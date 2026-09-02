"""Protocolo ASCII do fabricante (DPCL - Pan-Tilt Command Language).

Este é o protocolo de comando serial usado pelas unidades Pan-Tilt da
FLIR / Directed Perception (PTU-D46, D48E, D100E, D300E — família
"E-Series" e anteriores são compatíveis com o mesmo conjunto básico de
comandos). O formato de comando e resposta implementado aqui foi
verificado contra o driver de código aberto `flir_pantilt_d46`
(cburbridge/flir_pantilt_d46, arquivo src/ptu46_driver.cc), que fala com
hardware real:

    - Comando de eixo: "<eixo><código>[valor] " (ex.: "PP1000 " define a
      posição de pan; "PP " sem valor consulta a posição atual de pan).
    - Resposta numérica de consulta: "*<eixo minúsculo><valor>" (ex.:
      "*p1500"). Confirmado lendo GetPosition()/GetSpeed() do driver
      citado, que faz strtod(&buffer[2], ...) após checar buffer[0]=='*'.
    - Comando de reset ("R" / " r "): resposta "!T!T!P!P*" (idem, valor
      hardcoded checado pelo driver após o reset).

Os demais comandos (aceleração, base speed, limites de velocidade/posição,
modos de controle, echo, feedback verboso/terso, save/restore de
defaults) seguem a nomenclatura documentada publicamente para a "Pan-Tilt
Command Language" (mesma família de comandos usada desde o PTU-D46 até o
D300E). O acesso automatizado aos PDFs oficiais da FLIR para conferir
byte-a-byte cada resposta foi bloqueado pela política de rede desta
sessão (ver docs/PROTOCOL.md para a lista de fontes tentadas e o que foi
efetivamente confirmado). Onde o formato exato da resposta não pôde ser
confirmado, foi adotada uma convenção consistente com o padrão
confirmado ("*" para sucesso, "!" para erro) — ajuste em protocol.py se o
seu firmware real usar um formato diferente.
"""

from __future__ import annotations

import re
import time

from .device import ControlMode, PanTiltDevice

_AXIS_ATTR_BY_CODE = {
    "S": "desired_speed",
    "A": "acceleration",
    "B": "base_speed",
    "U": "upper_speed_limit",
    "L": "lower_speed_limit",
    "N": "min_limit",
    "X": "max_limit",
}

_GLOBAL_TWO_CHAR = {
    "CI", "CV", "FT", "FV", "ED", "EE", "LE", "LD", "DF", "DS", "DR",
}

_GLOBAL_ONE_CHAR = {"H", "A", "I", "S", "R", "V", "C", "F", "E", "L", "D"}

_TOKEN_RE = re.compile(r"\s+")


class ProtocolError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DPCLProtocol:
    """Interpreta bytes recebidos e produz bytes de resposta, contra um PanTiltDevice."""

    def __init__(self, device: PanTiltDevice, on_command=None):
        self.device = device
        self._buffer = ""
        self._saved_defaults: dict | None = None
        self.on_command = on_command  # callback opcional(token:str, response:str) para log/GUI

    # ------------------------------------------------------------------
    def feed(self, data: bytes) -> bytes:
        text = data.decode("ascii", errors="ignore")
        self._buffer += text
        out = []
        while True:
            m = _TOKEN_RE.search(self._buffer)
            if not m:
                break
            token = self._buffer[: m.start()]
            self._buffer = self._buffer[m.end():]
            if token:
                out.append(self._process_token(token))
        return "".join(out).encode("ascii", errors="replace")

    # ------------------------------------------------------------------
    def _process_token(self, raw_token: str) -> str:
        token = raw_token.upper()
        echo_was_enabled = self.device.echo_enabled
        try:
            response_body = self._execute(token)
        except ProtocolError as exc:
            response_body = f"!{exc.code} {exc.message}\r\n"
        except Exception as exc:  # defesa contra qualquer bug de parsing
            response_body = f"!9 Internal error: {exc}\r\n"

        if echo_was_enabled:
            result = f"{raw_token}\r\n{response_body}"
        else:
            result = response_body

        if self.on_command is not None:
            self.on_command(raw_token, result)
        return result

    # ------------------------------------------------------------------
    def _execute(self, token: str) -> str:
        first = token[0]
        if first in ("P", "T"):
            return self._execute_axis_command(token)
        return self._execute_global_command(token)

    def _axis(self, letter: str):
        return self.device.pan if letter == "P" else self.device.tilt

    def _execute_axis_command(self, token: str) -> str:
        axis_letter = token[0]
        axis = self._axis(axis_letter)
        rest = token[1:]
        if not rest:
            raise ProtocolError(1, f"Missing axis command code in '{token}'")

        code = rest[0]
        value_str = rest[1:]

        if code == "P":
            return self._axis_position(axis, axis_letter, value_str)
        if code == "O":
            return self._axis_offset(axis, axis_letter, value_str)
        if code == "H":
            if value_str:
                raise ProtocolError(2, "Halt command takes no value")
            axis.halt()
            return self._ack(f"{axis_letter} HALT")
        if code in _AXIS_ATTR_BY_CODE:
            return self._axis_attribute(axis, axis_letter, code, value_str)

        raise ProtocolError(1, f"Unknown axis command code '{code}'")

    def _axis_position(self, axis, axis_letter: str, value_str: str) -> str:
        if value_str == "":
            return self._query(axis_letter, axis.position)
        value = self._parse_int(value_str)
        axis.set_target_position(value)
        return self._ack(f"{axis_letter} POSITION -> {value}")

    def _axis_offset(self, axis, axis_letter: str, value_str: str) -> str:
        if value_str == "":
            return self._query(axis_letter, 0)
        value = self._parse_int(value_str)
        axis.offset_target_position(value)
        return self._ack(f"{axis_letter} OFFSET {value}")

    def _axis_attribute(self, axis, axis_letter: str, code: str, value_str: str) -> str:
        attr = _AXIS_ATTR_BY_CODE[code]
        if value_str == "":
            return self._query(axis_letter, getattr(axis, attr))
        value = self._parse_int(value_str)
        setattr(axis, attr, value)
        return self._ack(f"{axis_letter}{code} -> {value}")

    # ------------------------------------------------------------------
    def _execute_global_command(self, token: str) -> str:
        if token in _GLOBAL_TWO_CHAR:
            return self._global_two_char(token)

        code = token[0]
        value_str = token[1:]

        if code == "H":
            self.device.halt_all()
            return self._ack("HALT ALL")
        if code == "A":
            return self._await_completion()
        if code == "I":
            self.device.slaved_execution = False
            return self._ack("EXEC MODE -> IMMEDIATE")
        if code == "S":
            self.device.slaved_execution = True
            return self._ack("EXEC MODE -> SLAVED")
        if code == "R":
            self.device.reset()
            return "!T!T!P!P*\r\n"
        if code == "V":
            return f"* {self.device.firmware_version}\r\n"
        if code in ("C", "F", "E", "L", "D") and value_str == "":
            return self._global_query(code)

        raise ProtocolError(1, f"Unknown command '{token}'")

    def _global_two_char(self, token: str) -> str:
        if token == "CI":
            self.device.control_mode = ControlMode.POSITION
            return self._ack("CONTROL MODE -> POSITION")
        if token == "CV":
            self.device.control_mode = ControlMode.VELOCITY
            return self._ack("CONTROL MODE -> VELOCITY")
        if token == "FT":
            self.device.verbose_feedback = False
            return self._ack("FEEDBACK -> TERSE")
        if token == "FV":
            self.device.verbose_feedback = True
            return self._ack("FEEDBACK -> VERBOSE")
        if token == "ED":
            self.device.echo_enabled = False
            return self._ack("ECHO -> DISABLED")
        if token == "EE":
            self.device.echo_enabled = True
            return self._ack("ECHO -> ENABLED")
        if token == "LE":
            self.device.pan.limits_enabled = True
            self.device.tilt.limits_enabled = True
            return self._ack("LIMITS -> ENABLED")
        if token == "LD":
            self.device.pan.limits_enabled = False
            self.device.tilt.limits_enabled = False
            return self._ack("LIMITS -> DISABLED")
        if token == "DF":
            self.device.reset()
            return self._ack("FACTORY DEFAULTS RESTORED")
        if token == "DS":
            self._saved_defaults = self._capture_settings()
            return self._ack("SETTINGS SAVED")
        if token == "DR":
            if self._saved_defaults is not None:
                self._restore_settings(self._saved_defaults)
            return self._ack("SETTINGS RESTORED")
        raise ProtocolError(1, f"Unknown command '{token}'")

    def _global_query(self, code: str) -> str:
        if code == "C":
            return f"* {self.device.control_mode.value}\r\n"
        if code == "F":
            return f"* {'verbose' if self.device.verbose_feedback else 'terse'}\r\n"
        if code == "E":
            return f"* {'enabled' if self.device.echo_enabled else 'disabled'}\r\n"
        if code == "L":
            state = self.device.pan.limits_enabled and self.device.tilt.limits_enabled
            return f"* {'enabled' if state else 'disabled'}\r\n"
        if code == "D":
            return self._ack("no default action")
        raise ProtocolError(1, f"Unknown query '{code}'")

    def _await_completion(self, timeout: float = 30.0) -> str:
        start = time.monotonic()
        while self.device.is_in_motion():
            if time.monotonic() - start > timeout:
                break
            time.sleep(0.02)
        return self._ack("MOTION COMPLETE")

    # ------------------------------------------------------------------
    def _capture_settings(self) -> dict:
        def axis_settings(axis):
            return {
                "desired_speed": axis.desired_speed,
                "base_speed": axis.base_speed,
                "acceleration": axis.acceleration,
                "upper_speed_limit": axis.upper_speed_limit,
                "lower_speed_limit": axis.lower_speed_limit,
                "min_limit": axis.min_limit,
                "max_limit": axis.max_limit,
                "limits_enabled": axis.limits_enabled,
            }

        return {"pan": axis_settings(self.device.pan), "tilt": axis_settings(self.device.tilt)}

    def _restore_settings(self, saved: dict) -> None:
        for axis_name, axis in (("pan", self.device.pan), ("tilt", self.device.tilt)):
            for key, value in saved[axis_name].items():
                setattr(axis, key, value)

    # ------------------------------------------------------------------
    def _parse_int(self, value_str: str) -> int:
        try:
            return int(value_str)
        except ValueError:
            raise ProtocolError(2, f"Invalid integer value '{value_str}'")

    def _ack(self, description: str) -> str:
        if self.device.verbose_feedback:
            return f"* OK {description}\r\n"
        return "*\r\n"

    def _query(self, axis_letter: str, value) -> str:
        if self.device.verbose_feedback:
            return f"* {axis_letter} = {value}\r\n"
        return f"*{axis_letter.lower()}{value}\r\n"
