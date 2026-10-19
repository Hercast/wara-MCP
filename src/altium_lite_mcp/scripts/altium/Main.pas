{ wara DelphiScript project, dispatcher and commands.
  Apache-2.0. EXPERIMENTAL and UNTESTED against a real Altium install.

  Run via: X2.EXE -RScriptingSystem:RunScript(ProjectName="...\Altium_Lite.PrjScr"|ProcName="Main>Run")

  Every Altium API call below follows commonly used DelphiScript names but has NOT
  been run yet. Verify with the spikes in docs/ACCEPTANCE.md. Open points:
    - Altium version lookup returns 'unknown'
    - sheets that are not open are skipped by the edit commands
    - undo grouping is per sheet (and per PCB), not per call
    - delete_parameters / save_project / compile_messages use the least certain API names
    - PCB commands act on the focused PCB document (PCBServer.GetCurrentPCBBoard)
  Only integers cross the wire (IU = internal units, 1 mil = 10000 IU; angle in
  centidegrees) so decimal separators of the Windows locale cannot interfere. }

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

function BoolJson(B : Boolean) : String;
begin
  if B then Result := 'true' else Result := 'false';
end;

function CountOf(Req : TStringList; Key : String) : Integer;
begin
  Result := 0;
  if Req.Values[Key] <> '' then Result := StrToInt(Req.Values[Key]);
end;

{ ---- status ---------------------------------------------------------------- }

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

{ ---- reads ----------------------------------------------------------------- }

function SheetsJson(Proj : IProject) : String;
var
  I : Integer;
  Doc : IDocument;
  Srv : IServerDocument;
  IsOpen, IsMod : Boolean;
begin
  Result := '';
  for I := 0 to Proj.DM_LogicalDocumentCount - 1 do
  begin
    Doc := Proj.DM_LogicalDocuments(I);
    if Doc.DM_DocumentKind <> 'SCH' then Continue;
    Srv := Client.GetDocumentByPath(Doc.DM_FullPath);
    IsOpen := (Srv <> nil);
    IsMod := False;
    if IsOpen then IsMod := Srv.Modified;
    if Result <> '' then Result := Result + ',';
    Result := Result + '{"name":' + JsonStr(Doc.DM_FileName) + ',"open":' + BoolJson(IsOpen) +
              ',"modified":' + BoolJson(IsMod) + '}';
  end;
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
  Seen : TStringList;
  I, J, K, WantedCount : Integer;
  WithPins : Boolean;
  Des, Params, Pins, Item, Items, Key : String;
begin
  Proj := GetWorkspace.DM_FocusedProject;
  Proj.DM_Compile;
  WantedCount := CountOf(Req, 'designator.count');
  WithPins := (Req.Values['include_pins'] = 'true');
  Items := '';
  Seen := TStringList.Create;
  try
    for I := 0 to Proj.DM_LogicalDocumentCount - 1 do
    begin
      Doc := Proj.DM_LogicalDocuments(I);
      if Doc.DM_DocumentKind <> 'SCH' then Continue;
      for J := 0 to Doc.DM_ComponentCount - 1 do
      begin
        Comp := Doc.DM_Components(J);
        Des := Comp.DM_LogicalDesignator;
        // Multi-part components repeat on the same sheet with the same library ref;
        // true duplicate designators (other sheet or other part) are kept so they can be reported.
        Key := UpperCase(Des) + '|' + Doc.DM_FileName + '|' + Comp.DM_LibraryReference;
        if Seen.IndexOf(Key) >= 0 then Continue;
        if not WantedContains(Req, WantedCount, Des) then Continue;
        Seen.Add(Key);

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
        if Items <> '' then Items := Items + ',';
        Items := Items + Item + '}';
      end;
    end;
  finally
    Seen.Free;
  end;
  Result := '{"components":[' + Items + '],"sheets":[' + SheetsJson(Proj) + '],"project_name":' +
            JsonStr(Proj.DM_ProjectFileName) + '}';
end;

function CmdCompileMessages : String;
var
  Proj : IProject;
  V    : IViolation;
  I    : Integer;
  Items : String;
begin
  Proj := GetWorkspace.DM_FocusedProject;
  Proj.DM_Compile;
  Items := '';
  for I := 0 to Proj.DM_ViolationCount - 1 do
  begin
    V := Proj.DM_Violations(I);
    if Items <> '' then Items := Items + ',';
    // document name left empty until the owner-document accessor is verified
    Items := Items + '{"severity":' + JsonStr(V.DM_ErrorLevelString) +
             ',"text":' + JsonStr(V.DM_LongDescriptorString) + ',"document":""}';
  end;
  Result := '{"messages":[' + Items + ']}';
end;

{ ---- schematic parameter edits (op = set | rename | delete) ----------------- }

function CmdParamOp(Req : TStringList; Op : String) : String;
var
  Proj   : IProject;
  Doc    : IDocument;
  SchDoc : ISch_Document;
  Comp   : ISch_Component;
  P      : ISch_Parameter;
  Status : TStringList;
  I, J, N : Integer;
  Des, Name, Value, NewName, OutJson : String;
  Create : Boolean;
begin
  Proj := GetWorkspace.DM_FocusedProject;
  N := CountOf(Req, 'change.count');
  Create := (Req.Values['create_if_missing'] = 'true');
  Status := TStringList.Create;
  try
    for I := 0 to N - 1 do Status.Add('not_found');

    for J := 0 to Proj.DM_LogicalDocumentCount - 1 do
    begin
      Doc := Proj.DM_LogicalDocuments(J);
      if Doc.DM_DocumentKind <> 'SCH' then Continue;
      SchDoc := SchServer.GetSchDocumentByPath(Doc.DM_FullPath);
      if SchDoc = nil then Continue;   // sheet not open: skipped (Python refuses these up front)

      SchServer.ProcessControl.PreProcess(SchDoc, '');
      try
        for I := 0 to N - 1 do
        begin
          if Status[I] = 'ok' then Continue;
          Des := ReqValue(Req, 'change.' + IntToStr(I) + '.designator');
          Name := ReqValue(Req, 'change.' + IntToStr(I) + '.name');
          Value := ReqValue(Req, 'change.' + IntToStr(I) + '.value');
          NewName := ReqValue(Req, 'change.' + IntToStr(I) + '.new_name');
          Comp := FindComponentInSheet(SchDoc, Des);
          if Comp = nil then Continue;

          P := FindParameter(Comp, Name);
          if Op = 'set' then
          begin
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
          end
          else if P <> nil then
          begin
            if Op = 'rename' then
            begin
              SchBeginModify(P);
              P.Name := NewName;
              SchEndModify(P);
              Status[I] := 'ok';
            end
            else if Op = 'delete' then
            begin
              SchServer.RobotManager.SendMessage(Comp.I_ObjectAddress, c_BroadCast, SCHM_BeginModify, c_NoEventData);
              Comp.RemoveSchObject(P);
              SchServer.RobotManager.SendMessage(Comp.I_ObjectAddress, c_BroadCast, SCHM_EndModify, c_NoEventData);
              Status[I] := 'ok';
            end;
          end;
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

{ ---- PCB ------------------------------------------------------------------- }

function CmdGetPositions(Req : TStringList) : String;
var
  Board : IPCB_Board;
  Comp  : IPCB_Component;
  I, N  : Integer;
  Des, Items : String;
begin
  Board := PCBServer.GetCurrentPCBBoard;
  if Board = nil then
  begin
    Result := '';
    Exit;
  end;
  N := CountOf(Req, 'designator.count');
  Items := '';
  for I := 0 to N - 1 do
  begin
    Des := ReqValue(Req, 'designator.' + IntToStr(I));
    Comp := Board.GetPcbComponentByRefDes(Des);
    if Comp = nil then Continue;
    if Items <> '' then Items := Items + ',';
    Items := Items + '{"designator":' + JsonStr(Des) +
             ',"x_iu":' + IntToStr(Comp.x - Board.XOrigin) +
             ',"y_iu":' + IntToStr(Comp.y - Board.YOrigin) +
             ',"rotation_cd":' + IntToStr(Round(Comp.Rotation * 100)) + '}';
  end;
  Result := '{"positions":[' + Items + ']}';
end;

function CmdMoveComponents(Req : TStringList) : String;
var
  Board : IPCB_Board;
  Comp  : IPCB_Component;
  I, N  : Integer;
  Des, Items, St : String;
begin
  Board := PCBServer.GetCurrentPCBBoard;
  if Board = nil then
  begin
    Result := '';
    Exit;
  end;
  N := CountOf(Req, 'change.count');
  Items := '';
  PCBServer.PreProcess;
  try
    for I := 0 to N - 1 do
    begin
      Des := ReqValue(Req, 'change.' + IntToStr(I) + '.designator');
      Comp := Board.GetPcbComponentByRefDes(Des);
      St := 'not_found';
      if Comp <> nil then
      begin
        PCBServer.SendMessageToRobots(Comp.I_ObjectAddress, c_Broadcast, PCBM_BeginModify, c_NoEventData);
        Comp.Rotation := StrToInt(Req.Values['change.' + IntToStr(I) + '.rotation_cd']) / 100;
        Comp.MoveToXY(StrToInt(Req.Values['change.' + IntToStr(I) + '.x_iu']) + Board.XOrigin,
                      StrToInt(Req.Values['change.' + IntToStr(I) + '.y_iu']) + Board.YOrigin);
        PCBServer.SendMessageToRobots(Comp.I_ObjectAddress, c_Broadcast, PCBM_EndModify, c_NoEventData);
        St := 'ok';
      end;
      if Items <> '' then Items := Items + ',';
      Items := Items + '{"designator":' + JsonStr(Des) + ',"status":' + JsonStr(St) + '}';
    end;
  finally
    PCBServer.PostProcess;
  end;
  Board.ViewManager_FullUpdate;
  Result := '{"results":[' + Items + ']}';
end;

{ ---- save ------------------------------------------------------------------ }

function CmdSaveProject : String;
var
  Proj : IProject;
  Doc  : IDocument;
  Srv  : IServerDocument;
  I    : Integer;
  Saved, Failed : String;
begin
  Proj := GetWorkspace.DM_FocusedProject;
  Saved := '';
  Failed := '';
  for I := 0 to Proj.DM_LogicalDocumentCount - 1 do
  begin
    Doc := Proj.DM_LogicalDocuments(I);
    if Doc.DM_DocumentKind <> 'SCH' then Continue;
    Srv := Client.GetDocumentByPath(Doc.DM_FullPath);
    if (Srv = nil) or (not Srv.Modified) then Continue;
    Srv.DoFileSave(Doc.DM_DocumentKind);
    if Srv.Modified then
    begin
      if Failed <> '' then Failed := Failed + ',';
      Failed := Failed + JsonStr(Doc.DM_FileName);
    end
    else
    begin
      if Saved <> '' then Saved := Saved + ',';
      Saved := Saved + JsonStr(Doc.DM_FileName);
    end;
  end;
  Result := '{"saved":[' + Saved + '],"failed":[' + Failed + ']}';
end;

{ ---- dispatcher ------------------------------------------------------------ }

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
      else if Cmd = 'compile_messages' then Data := CmdCompileMessages
      else if Cmd = 'set_parameters' then Data := CmdParamOp(Req, 'set')
      else if Cmd = 'rename_parameters' then Data := CmdParamOp(Req, 'rename')
      else if Cmd = 'delete_parameters' then Data := CmdParamOp(Req, 'delete')
      else if Cmd = 'get_positions' then Data := CmdGetPositions(Req)
      else if Cmd = 'move_components' then Data := CmdMoveComponents(Req)
      else if Cmd = 'save_project' then Data := CmdSaveProject
      else
      begin
        WriteResponse(Id, False, '', 'E_ALTIUM_ERROR', 'Unknown command: ' + Cmd);
        Exit;
      end;
      if Data = '' then
      begin
        WriteResponse(Id, False, '', 'E_NO_PROJECT', 'No PCB document is open and focused in Altium.');
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
