{ altium-lite-mcp DelphiScript project, dispatcher and commands.
  Apache-2.0. EXPERIMENTAL and UNTESTED against a real Altium install.

  Run via: X2.EXE -RScriptingSystem:RunScript(ProjectName="...\Altium_Lite.PrjScr"|ProcName="Main>Run")

  Every Altium API call below follows the documented/commonly used DelphiScript
  names but has NOT been run yet. Verify with spikes S1-S5 in docs/ACCEPTANCE.md.
  Known open points: Altium version lookup (returns 'unknown'), opening sheets
  that are not already open (they are skipped), undo grouping across sheets. }

function FindComponentInSheet(SchDoc : ISch_Document; Des : String) : ISch_Component;
var
  It : ISch_Iterator;
  C  : ISch_Component;
begin
  Result := nil;
  It := SchDoc.SchIterator_Create;
  It.AddFilter_ObjectSet(MkSet(eSchComponent));
  try
    C := It.FirstSchObject;
    while C <> nil do
    begin
      if UpperCase(C.Designator.Text) = UpperCase(Des) then
      begin
        Result := C;
        Break;
      end;
      C := It.NextSchObject;
    end;
  finally
    SchDoc.SchIterator_Destroy(It);
  end;
end;

function FindParameter(Comp : ISch_Component; Name : String) : ISch_Parameter;
var
  It : ISch_Iterator;
  P  : ISch_Parameter;
begin
  Result := nil;
  It := Comp.SchIterator_Create;
  It.AddFilter_ObjectSet(MkSet(eParameter));
  try
    P := It.FirstSchObject;
    while P <> nil do
    begin
      if UpperCase(P.Name) = UpperCase(Name) then
      begin
        Result := P;
        Break;
      end;
      P := It.NextSchObject;
    end;
  finally
    Comp.SchIterator_Destroy(It);
  end;
end;

function CmdStatus : String;
var
  Proj : IProject;
begin
  Proj := GetWorkspace.DM_FocusedProject;
  Result := '{"altium_version":"unknown","script_version":' + JsonStr(ScriptVersion);
  if Proj = nil then
    Result := Result + ',"project_name":null,"project_path":null}'
  else
    Result := Result + ',"project_name":' + JsonStr(Proj.DM_ProjectFileName) +
              ',"project_path":' + JsonStr(Proj.DM_ProjectFullPath) + '}';
end;

function WantedContains(Req : TStringList; Count : Integer; Des : String) : Boolean;
var
  I : Integer;
begin
  Result := (Count = 0);
  for I := 0 to Count - 1 do
    if UpperCase(ReqValue(Req, 'designator.' + IntToStr(I))) = UpperCase(Des) then
    begin
      Result := True;
      Break;
    end;
end;

function CmdGetComponents(Req : TStringList) : String;
var
  Proj : IProject;
  Doc  : IDocument;
  Comp : IComponent;
  Seen, Items : TStringList;
  I, J, K, WantedCount : Integer;
  WithPins : Boolean;
  Des, Params, Pins, Item : String;
begin
  Result := '';
  Proj := GetWorkspace.DM_FocusedProject;
  if Proj = nil then Exit;
  Proj.DM_Compile;
  WantedCount := 0;
  if Req.Values['designator.count'] <> '' then WantedCount := StrToInt(Req.Values['designator.count']);
  WithPins := (Req.Values['include_pins'] = 'true');
  Seen := TStringList.Create;
  Items := TStringList.Create;
  try
    for I := 0 to Proj.DM_LogicalDocumentCount - 1 do
    begin
      Doc := Proj.DM_LogicalDocuments(I);
      if Doc.DM_DocumentKind <> 'SCH' then Continue;
      for J := 0 to Doc.DM_ComponentCount - 1 do
      begin
        Comp := Doc.DM_Components(J);
        Des := Comp.DM_LogicalDesignator;
        if Seen.IndexOf(UpperCase(Des)) >= 0 then Continue;   // multi-part components
        if not WantedContains(Req, WantedCount, Des) then Continue;
        Seen.Add(UpperCase(Des));

        Params := '';
        for K := 0 to Comp.DM_ParameterCount - 1 do
        begin
          if Params <> '' then Params := Params + ',';
          Params := Params + JsonStr(Comp.DM_Parameters(K).DM_Name) + ':' + JsonStr(Comp.DM_Parameters(K).DM_Value);
        end;

        Item := '{"designator":' + JsonStr(Des) +
                ',"comment":' + JsonStr(Comp.DM_Comment) +
                ',"library_ref":' + JsonStr(Comp.DM_LibraryReference) +
                ',"footprint":' + JsonStr(Comp.DM_FootPrint) +
                ',"sheet":' + JsonStr(Doc.DM_FileName) +
                ',"parameters":{' + Params + '}';
        if WithPins then
        begin
          Pins := '';
          for K := 0 to Comp.DM_PinCount - 1 do
          begin
            if Pins <> '' then Pins := Pins + ',';
            Pins := Pins + '{"number":' + JsonStr(Comp.DM_Pins(K).DM_PinNumber) +
                    ',"name":' + JsonStr(Comp.DM_Pins(K).DM_PinName) +
                    ',"net":' + JsonStr(Comp.DM_Pins(K).DM_FlattenedNetName) + '}';
          end;
          Item := Item + ',"pins":[' + Pins + ']';
        end;
        Items.Add(Item + '}');
      end;
    end;
    Result := '{"components":[';
    for I := 0 to Items.Count - 1 do
    begin
      if I > 0 then Result := Result + ',';
      Result := Result + Items[I];
    end;
    Result := Result + ']}';
  finally
    Seen.Free;
    Items.Free;
  end;
end;

function CmdSetParameters(Req : TStringList) : String;
var
  Proj   : IProject;
  Doc    : IDocument;
  SchDoc : ISch_Document;
  Comp   : ISch_Component;
  P      : ISch_Parameter;
  Status : TStringList;
  I, J, N : Integer;
  Des, Name, Value, OutJson : String;
  Create : Boolean;
begin
  Result := '';
  Proj := GetWorkspace.DM_FocusedProject;
  if Proj = nil then Exit;
  N := 0;
  if Req.Values['change.count'] <> '' then N := StrToInt(Req.Values['change.count']);
  Create := (Req.Values['create_if_missing'] = 'true');
  Status := TStringList.Create;
  try
    for I := 0 to N - 1 do Status.Add('not_found');

    for J := 0 to Proj.DM_LogicalDocumentCount - 1 do
    begin
      Doc := Proj.DM_LogicalDocuments(J);
      if Doc.DM_DocumentKind <> 'SCH' then Continue;
      SchDoc := SchServer.GetSchDocumentByPath(Doc.DM_FullPath);
      if SchDoc = nil then Continue;   // sheet not open: skipped (see header)

      SchServer.ProcessControl.PreProcess(SchDoc, '');
      try
        for I := 0 to N - 1 do
        begin
          if Status[I] = 'ok' then Continue;
          Des := ReqValue(Req, 'change.' + IntToStr(I) + '.designator');
          Name := ReqValue(Req, 'change.' + IntToStr(I) + '.name');
          Value := ReqValue(Req, 'change.' + IntToStr(I) + '.value');
          Comp := FindComponentInSheet(SchDoc, Des);
          if Comp = nil then Continue;

          P := FindParameter(Comp, Name);
          if P <> nil then
          begin
            SchBeginModify(P);
            P.Text := Value;
            SchEndModify(P);
            Status[I] := 'ok';
          end
          else if Create then
          begin
            P := SchServer.SchObjectFactory(eParameter, eCreate_Default);
            P.Name := Name;
            P.Text := Value;
            P.ShowName := False;
            P.IsHidden := True;
            Comp.AddSchObject(P);
            SchServer.RobotManager.SendMessage(Comp.I_ObjectAddress, c_BroadCast, SCHM_PrimitiveRegistration, P.I_ObjectAddress);
            Status[I] := 'ok';
          end
          else Status[I] := 'refused';
        end;
      finally
        SchServer.ProcessControl.PostProcess(SchDoc, '');
      end;
      SchDoc.GraphicallyInvalidate;
    end;

    OutJson := '';
    for I := 0 to N - 1 do
    begin
      if OutJson <> '' then OutJson := OutJson + ',';
      OutJson := OutJson + '{"designator":' + JsonStr(ReqValue(Req, 'change.' + IntToStr(I) + '.designator')) +
             ',"name":' + JsonStr(ReqValue(Req, 'change.' + IntToStr(I) + '.name')) +
             ',"status":' + JsonStr(Status[I]) + '}';
    end;
    Result := '{"results":[' + OutJson + '],"modified_unsaved":true}';
  finally
    Status.Free;
  end;
end;

procedure Run;
var
  Req  : TStringList;
  Id, Cmd, Data : String;
  Path : String;
begin
  Path := ExchangeDir + '\request.txt';
  if not FileExists(Path) then Exit;     // stale launch: nothing to do
  Req := TStringList.Create;
  try
    Req.LoadFromFile(Path);
    DeleteFile(Path);                     // consume the request exactly once
    Id := Req.Values['id'];
    Cmd := Req.Values['command'];
    if Req.Values['protocol'] <> ProtocolVersion then
    begin
      WriteResponse(Id, False, '', 'E_SCRIPT_VERSION', 'Protocol mismatch');
      Exit;
    end;
    try
      if Cmd = 'status' then Data := CmdStatus
      else if GetWorkspace.DM_FocusedProject = nil then
      begin
        WriteResponse(Id, False, '', 'E_NO_PROJECT', 'No project is open in Altium.');
        Exit;
      end
      else if Cmd = 'get_components' then Data := CmdGetComponents(Req)
      else if Cmd = 'set_parameters' then Data := CmdSetParameters(Req)
      else
      begin
        WriteResponse(Id, False, '', 'E_ALTIUM_ERROR', 'Unknown command: ' + Cmd);
        Exit;
      end;
      WriteResponse(Id, True, Data, '', '');
    except
      WriteResponse(Id, False, '', 'E_ALTIUM_ERROR', 'Script runtime error in command ' + Cmd);
    end;
  finally
    Req.Free;
  end;
end;
