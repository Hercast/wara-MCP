{ altium-lite-mcp DelphiScript project, request/response helpers.
  Apache-2.0. EXPERIMENTAL and UNTESTED against a real Altium install.

  Requests are key=value lines (read with TStringList.Values), values are
  ASCII-escaped: \\ \n \r \uXXXX. Responses are JSON written by string
  concatenation with JsonEscape. }

function Hex4(N : Integer) : String;
const
  Digits = '0123456789ABCDEF';
begin
  Result := Digits[(N div 4096) mod 16 + 1] + Digits[(N div 256) mod 16 + 1] +
            Digits[(N div 16) mod 16 + 1] + Digits[N mod 16 + 1];
end;

function JsonEscape(S : String) : String;
var
  I, C : Integer;
begin
  Result := '';
  for I := 1 to Length(S) do
  begin
    C := Ord(S[I]);
    if S[I] = '"' then Result := Result + '\"'
    else if S[I] = '\' then Result := Result + '\\'
    else if (C < 32) or (C > 126) then Result := Result + '\u' + Hex4(C)
    else Result := Result + S[I];
  end;
end;

function JsonStr(S : String) : String;
begin
  Result := '"' + JsonEscape(S) + '"';
end;

function UnescapeValue(S : String) : String;
var
  I : Integer;
  N : String;
begin
  Result := '';
  I := 1;
  while I <= Length(S) do
  begin
    if (S[I] = '\') and (I < Length(S)) then
    begin
      N := S[I + 1];
      if N = '\' then begin Result := Result + '\'; I := I + 2; end
      else if N = 'n' then begin Result := Result + Chr(10); I := I + 2; end
      else if N = 'r' then begin Result := Result + Chr(13); I := I + 2; end
      else if (N = 'u') and (I + 5 <= Length(S)) then
      begin
        Result := Result + Chr(StrToInt('$' + Copy(S, I + 2, 4)));
        I := I + 6;
      end
      else begin Result := Result + S[I]; I := I + 1; end;
    end
    else begin Result := Result + S[I]; I := I + 1; end;
  end;
end;

function ReqValue(Req : TStringList; Key : String) : String;
begin
  Result := UnescapeValue(Req.Values[Key]);
end;

procedure WriteResponse(Id : String; Success : Boolean; DataJson : String; ErrCode : String; ErrMsg : String);
var
  Resp : TStringList;
  Body : String;
begin
  Body := '{"id":' + JsonStr(Id) + ',"protocol_version":' + ProtocolVersion +
          ',"script_version":' + JsonStr(ScriptVersion);
  if Success then
    Body := Body + ',"success":true,"data":' + DataJson + ',"error":null}'
  else
    Body := Body + ',"success":false,"data":null,"error":{"code":' + JsonStr(ErrCode) +
            ',"message":' + JsonStr(ErrMsg) + '}}';
  Resp := TStringList.Create;
  try
    Resp.Add(Body);
    Resp.SaveToFile(ExchangeDir + '\resp_' + Id + '.json');
  finally
    Resp.Free;
  end;
end;
