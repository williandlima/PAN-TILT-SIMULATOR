"""Protocolo ASCII do fabricante (DPCL - Pan-Tilt Command Language).

Protocolo de comando serial das unidades Pan-Tilt da FLIR / Directed
Perception (PTU-D46, D48E, D100E, D300E). O conjunto de comandos e o
formato das respostas implementados aqui foram verificados contra dois
drivers de código aberto que conversam com hardware PTU real:

``hmorris94/FLIR-PTU-Python`` (``flirptu/ptu.py``) — dele vêm os
comandos ``PR``/``TR`` (resolução), ``PO``/``TO`` (posição alvo),
``PD``/``TD`` (velocidade atual / delta), ``PNU``/``PXU``/``TNU``/``TXU``
(limites de usuário), ``LU``/``LE``/``LD``, ``RP``/``RT``/``RE``,
``PU``/``TU``, ``B`` (movimento combinado), ``@(baud,0,F)`` e — o mais
importante — os textos exatos das respostas em modo verboso, que aquele
driver fatia por offset fixo::

    "* Current Pan position is "     (26 caracteres)
    "* Current Tilt position is "    (27 caracteres)
    "* Target Pan position is "      (25 caracteres)
    "* Target Tilt position is "     (26 caracteres)

``cburbridge/flir_pantilt_d46`` (``src/ptu46_driver.cc``) — dele vêm o
formato de comando ``<eixo><código>[valor] ``, a sequência de
inicialização (``ft``, ``ed``, ``ci``, ``ld``, reset), a resposta fixa de
reset ``!T!T!P!P*`` e o formato terso ``* <valor>`` (ele valida
``buffer[0] == '*'`` e converte o restante após remover espaços).

Resumo do formato:

    - Comando: ``<eixo><código>[valor]`` terminado por espaço ou CR/LF.
      Sem valor, o comando vira uma consulta.
    - Resposta de sucesso: começa com ``*``; erro: começa com ``!``.
    - Modo terso (``FT``): ``* <valor>``.
    - Modo verboso (``FV``, padrão de fábrica): ``* <frase> <valor>``.

Os comandos ``G...`` (Geo Pointing Module, seção "GPM" da tabela) foram
verificados byte a byte contra fotos das páginas do Capítulo 17 do "E
Series Pan-Tilt Command Reference Manual, Version 6.00 (09/2014)" da
própria FLIR — ver ``pantiltsim/tracking.py`` (``GpmPose``) para o que
cada campo significa.

Ver ``docs/PROTOCOL.md`` para a tabela completa e para a marcação do que
é confirmado por hardware real versus o que segue a nomenclatura da
família DPCL sem confirmação byte a byte.
"""

from __future__ import annotations

import logging
import re
import time

from .device import ControlMode, LimitMode, PanTiltDevice, PowerMode, StepMode
from .tracking import GeoPoint, Landmark, look_angles

log = logging.getLogger(__name__)

_TOKEN_SPLIT_RE = re.compile(r"\s+")
_BAUD_RE = re.compile(r"^@\((\d+),(\d+),([A-Z])\)$")

# Geo Pointing Module (Capítulo 17 do E Series Command Reference Manual,
# v6.00 09/2014) — campos confirmados byte a byte contra o manual real.
# Ordenados do mais longo para o mais curto: como o valor vem colado ao
# código (ex.: "GLLA-23.5,..."), é preciso casar "GLLA" antes de "GL", e
# "GGD"/"GMA"/"GMN"/"GMD"/"GMC" antes de "GG"/"GM".
_GPM_SINGLE_FIELDS = {
    "GL": "latitude_deg",
    "GO": "longitude_deg",
    "GA": "altitude_m",
    "GR": "roll_deg",
    "GP": "pitch_deg",
    "GY": "yaw_deg",
    "GCP": "camera_pitch_offset_deg",
}
_GPM_COMBINED_FIELDS = {
    "GLLA": ("latitude_deg", "longitude_deg", "altitude_m"),
    "GRPY": ("roll_deg", "pitch_deg", "yaw_deg"),
}
_GPM_AIM_CODES = ("GGD", "GG")
_GPM_LANDMARK_CODES = ("GMA", "GMN", "GMD", "GMC", "GM")
_GPM_CODES_BY_LENGTH = sorted(
    list(_GPM_SINGLE_FIELDS)
    + list(_GPM_COMBINED_FIELDS)
    + list(_GPM_AIM_CODES)
    + list(_GPM_LANDMARK_CODES),
    key=len,
    reverse=True,
)

_STEP_MODE_BY_LETTER = {
    "F": StepMode.FULL,
    "H": StepMode.HALF,
    "Q": StepMode.QUARTER,
    "E": StepMode.EIGHTH,
    "A": StepMode.AUTO,
}

_MOVE_POWER_BY_LETTER = {
    "L": PowerMode.LOW,
    "R": PowerMode.REGULATED,
    "H": PowerMode.HIGH,
}

_HOLD_POWER_BY_LETTER = {
    "O": PowerMode.OFF,
    "L": PowerMode.LOW,
    "R": PowerMode.REGULATED,
}


class ProtocolError(Exception):
    """Erro de comando, devolvido ao cliente como resposta ``! <mensagem>``."""


class DPCLProtocol:
    """Interpreta bytes recebidos e devolve bytes de resposta."""

    def __init__(self, device: PanTiltDevice, on_command=None, await_timeout: float = 60.0):
        self.device = device
        self.on_command = on_command
        # Tempo máximo que o comando ``A`` segura o enlace esperando o
        # movimento terminar. Como no hardware real, nenhum outro comando é
        # processado enquanto o await está pendente; o limite existe apenas
        # para o enlace nunca ficar preso para sempre.
        self.await_timeout = await_timeout
        self._buffer = ""
        self._saved: dict | None = None

    # ------------------------------------------------------------------
    def feed(self, data: bytes) -> bytes:
        """Consome bytes do enlace serial e devolve os bytes de resposta.

        Aceita fluxo fragmentado: tokens incompletos ficam no buffer até
        chegar o terminador (espaço, CR ou LF).
        """
        self._buffer += data.decode("ascii", errors="ignore")
        out: list[str] = []
        while True:
            match = _TOKEN_SPLIT_RE.search(self._buffer)
            if not match:
                break
            token = self._buffer[: match.start()]
            self._buffer = self._buffer[match.end():]
            if token:
                out.append(self._process_token(token))
        return "".join(out).encode("ascii", errors="replace")

    def execute_line(self, line: str) -> str:
        """Atalho para testes/GUI: executa uma linha de comandos e devolve texto."""
        if not line.endswith((" ", "\r", "\n")):
            line += " "
        return self.feed(line.encode("ascii", errors="ignore")).decode("ascii")

    # ------------------------------------------------------------------
    def _process_token(self, raw_token: str) -> str:
        token = raw_token.upper()
        echo_was_enabled = self.device.echo_enabled
        try:
            if token == "A":
                # Await não pode segurar o lock: o motor de simulação precisa girar.
                body = self._await_completion()
            else:
                with self.device.lock:
                    body = self._execute(token)
        except ProtocolError as exc:
            body = f"! {exc}\r\n"
        except Exception as exc:  # pragma: no cover - rede de segurança
            log.exception("Falha ao processar comando %r", raw_token)
            body = f"! Internal error: {exc}\r\n"

        result = f"{raw_token}\r\n{body}" if echo_was_enabled else body
        if self.on_command is not None:
            self.on_command(raw_token, result)
        return result

    def _execute(self, token: str) -> str:
        if token[0] in ("P", "T"):
            return self._execute_axis_command(token)
        return self._execute_global_command(token)

    # -- comandos de eixo ------------------------------------------------
    def _execute_axis_command(self, token: str) -> str:
        axis_letter = token[0]
        axis = self.device.pan if axis_letter == "P" else self.device.tilt
        axis_name = "Pan" if axis_letter == "P" else "Tilt"
        rest = token[1:]
        if not rest:
            raise ProtocolError(f"Incomplete command '{token}'")

        code, arg = rest[0], rest[1:]

        if code == "P":
            if arg == "":
                return self._value(axis.position, f"Current {axis_name} position is")
            self.device.request_target(axis.spec.name, self._parse_int(arg))
            return self._ok()

        if code == "O":
            if arg == "":
                return self._value(axis.target_position, f"Target {axis_name} position is")
            axis.offset_target_position(self._parse_int(arg))
            return self._ok()

        if code == "S":
            if arg == "":
                return self._value(axis.desired_speed, f"Target {axis_name} speed is")
            axis.set_desired_speed(self._parse_int(arg))
            return self._ok()

        if code == "D":
            if arg == "":
                return self._value(round(axis.current_speed), f"Current {axis_name} speed is")
            axis.offset_desired_speed(self._parse_int(arg))
            return self._ok()

        if code == "A":
            if arg == "":
                return self._value(axis.acceleration, f"{axis_name} acceleration is")
            axis.acceleration = self._parse_positive_int(arg)
            return self._ok()

        if code == "B":
            if arg == "":
                return self._value(axis.base_speed, f"{axis_name} base speed is")
            axis.base_speed = self._parse_positive_int(arg)
            return self._ok()

        if code == "U":
            if arg == "":
                return self._value(axis.upper_speed_limit, f"Maximum {axis_name} speed is")
            axis.upper_speed_limit = self._parse_positive_int(arg)
            return self._ok()

        if code == "L":
            if arg == "":
                return self._value(axis.lower_speed_limit, f"Minimum {axis_name} speed is")
            axis.lower_speed_limit = self._parse_positive_int(arg)
            return self._ok()

        if code == "N":
            return self._position_limit(axis, axis_name, arg, is_max=False)

        if code == "X":
            return self._position_limit(axis, axis_name, arg, is_max=True)

        if code == "R":
            if arg != "":
                raise ProtocolError("Resolution is read-only")
            return self._value(
                round(axis.arcsec_per_count, 4), f"{axis_name} resolution per position is"
            )

        if code == "M":
            if arg == "":
                return self._text(axis.move_power.value, f"{axis_name} move power is")
            axis.move_power = self._lookup(_MOVE_POWER_BY_LETTER, arg, "move power")
            return self._ok()

        if code == "H":
            if arg == "":
                return self._text(axis.hold_power.value, f"{axis_name} hold power is")
            axis.hold_power = self._lookup(_HOLD_POWER_BY_LETTER, arg, "hold power")
            return self._ok()

        raise ProtocolError(f"Unknown command '{token}'")

    def _position_limit(self, axis, axis_name: str, arg: str, is_max: bool) -> str:
        bound = "Maximum" if is_max else "Minimum"
        if arg == "":
            value = axis.effective_max if is_max else axis.effective_min
            return self._value(value, f"{bound} {axis_name} position is")
        if arg[0] != "U":
            raise ProtocolError(f"{bound} {axis_name} limit is set with the U (user) suffix")
        user_arg = arg[1:]
        if user_arg == "":
            value = axis.user_max if is_max else axis.user_min
            return self._value(value, f"{bound} user {axis_name} position is")
        counts = self._parse_int(user_arg)
        if is_max:
            axis.set_user_max(counts)
        else:
            axis.set_user_min(counts)
        return self._ok()

    # -- comandos globais --------------------------------------------------
    def _execute_global_command(self, token: str) -> str:
        if token.startswith("@"):
            return self._set_host_port(token)
        if token.startswith("B"):
            return self._combined_move(token)
        if token.startswith("W"):
            return self._step_mode(token)
        if token.startswith("G"):
            return self._gpm_command(token)

        code, arg = token[0], token[1:]

        if code == "H":
            return self._halt(arg)
        if code == "R":
            return self._reset(arg)
        if code == "C":
            return self._control_mode(arg)
        if code == "F":
            return self._feedback_mode(arg)
        if code == "E":
            return self._echo_mode(arg)
        if code == "L":
            return self._limit_mode(arg)
        if code == "D":
            return self._defaults(arg)
        if code == "M":
            return self._monitor(arg)
        if code == "I" and arg == "":
            self.device.slaved_execution = False
            self.device.apply_pending_targets()
            return self._ok()
        if code == "S" and arg == "":
            self.device.slaved_execution = True
            return self._ok()
        if code == "V" and arg == "":
            return self._text(self.device.firmware_version, "Version:")

        raise ProtocolError(f"Unknown command '{token}'")

    def _halt(self, arg: str) -> str:
        if arg == "":
            self.device.halt_all()
        elif arg == "P":
            self.device.pan.halt()
        elif arg == "T":
            self.device.tilt.halt()
        else:
            raise ProtocolError(f"Unknown halt command 'H{arg}'")
        return self._ok()

    def _reset(self, arg: str) -> str:
        if arg in ("", "E"):
            self.device.reset(pan=True, tilt=True)
        elif arg == "P":
            self.device.reset(pan=True, tilt=False)
        elif arg == "T":
            self.device.reset(pan=False, tilt=True)
        else:
            raise ProtocolError(f"Unknown reset command 'R{arg}'")
        # Resposta fixa confirmada no driver de referência para o reset.
        return "!T!T!P!P*\r\n"

    def _control_mode(self, arg: str) -> str:
        if arg == "":
            return self._text(self.device.control_mode.value, "Control mode is")
        if arg == "I":
            self.device.control_mode = ControlMode.POSITION
        elif arg == "V":
            self.device.control_mode = ControlMode.VELOCITY
        else:
            raise ProtocolError(f"Unknown control mode 'C{arg}'")
        return self._ok()

    def _feedback_mode(self, arg: str) -> str:
        if arg == "":
            return self._text("verbose" if self.device.verbose_feedback else "terse", "Feedback mode is")
        if arg == "T":
            self.device.verbose_feedback = False
        elif arg == "V":
            self.device.verbose_feedback = True
        else:
            raise ProtocolError(f"Unknown feedback mode 'F{arg}'")
        return self._ok()

    def _echo_mode(self, arg: str) -> str:
        if arg == "":
            return self._text("enabled" if self.device.echo_enabled else "disabled", "Echo is")
        if arg == "E":
            self.device.echo_enabled = True
        elif arg == "D":
            self.device.echo_enabled = False
        else:
            raise ProtocolError(f"Unknown echo command 'E{arg}'")
        return self._ok()

    def _limit_mode(self, arg: str) -> str:
        if arg == "":
            return self._text(self.device.limit_mode.value, "Limit mode is")
        modes = {"E": LimitMode.FACTORY, "U": LimitMode.USER, "D": LimitMode.DISABLED}
        if arg not in modes:
            raise ProtocolError(f"Unknown limit command 'L{arg}'")
        self.device.set_limit_mode(modes[arg])
        return self._ok()

    def _defaults(self, arg: str) -> str:
        if arg == "F":
            self.device.reset()
        elif arg == "S":
            self._saved = self._capture_settings()
        elif arg == "R":
            if self._saved is not None:
                self._restore_settings(self._saved)
        else:
            raise ProtocolError(f"Unknown defaults command 'D{arg}'")
        return self._ok()

    def _monitor(self, arg: str) -> str:
        if arg == "":
            return self._text("enabled" if self.device.monitor.enabled else "disabled", "Monitor mode is")
        if arg == "E":
            self.device.monitor.enabled = True
        elif arg == "D":
            self.device.monitor.enabled = False
            for axis in self.device.axes:
                axis.halt()
        else:
            raise ProtocolError(f"Unknown monitor command 'M{arg}'")
        return self._ok()

    def _step_mode(self, token: str) -> str:
        rest = token[1:]
        if not rest or rest[0] not in ("P", "T"):
            raise ProtocolError(f"Unknown command '{token}'")
        axis = self.device.pan if rest[0] == "P" else self.device.tilt
        axis_name = "Pan" if rest[0] == "P" else "Tilt"
        arg = rest[1:]
        if arg == "":
            return self._text(axis.step_mode.value, f"{axis_name} step mode is")
        axis.set_step_mode(self._lookup(_STEP_MODE_BY_LETTER, arg, "step mode"))
        return self._ok()

    def _combined_move(self, token: str) -> str:
        """Comando ``B<pan>,<tilt>,<vel_pan>,<vel_tilt>``: move os dois eixos juntos."""
        parts = token[1:].split(",")
        if len(parts) != 4:
            raise ProtocolError("Command B expects <pan>,<tilt>,<pan speed>,<tilt speed>")
        pan_pos, tilt_pos, pan_speed, tilt_speed = (self._parse_int(p) for p in parts)
        self.device.pan.set_desired_speed(abs(pan_speed))
        self.device.tilt.set_desired_speed(abs(tilt_speed))
        self.device.pan.set_target_position(pan_pos)
        self.device.tilt.set_target_position(tilt_pos)
        return self._ok()

    # -- Geo Pointing Module (GPM) — Capítulo 17 do manual real ---------------
    #
    # Comandos confirmados byte a byte contra fotos das páginas 99, 111 e
    # 113 do "E Series Pan-Tilt Command Reference Manual, Version 6.00
    # (09/2014)": posição própria da unidade (GL/GO/GA/GLLA, seção 17.3),
    # orientação própria (GR/GP/GY/GRPY/GCP, seção 17.4) e landmarks/aim
    # point (GM.../GG/GGD, seção 17.5). Ver pantiltsim/tracking.py
    # (GpmPose, Landmark, GeoTracker) e docs/PROTOCOL.md para o
    # detalhamento, as fontes, e o que do capítulo ainda não foi
    # confirmado (GC/GS/GDR/GT).
    def _gpm_command(self, token: str) -> str:
        for code in _GPM_CODES_BY_LENGTH:
            if not token.startswith(code):
                continue
            arg = token[len(code):]
            if code in _GPM_COMBINED_FIELDS:
                return self._gpm_combined(arg, _GPM_COMBINED_FIELDS[code])
            if code in _GPM_SINGLE_FIELDS:
                return self._gpm_single(arg, _GPM_SINGLE_FIELDS[code])
            if code == "GG":
                return self._gpm_aim(arg)
            if code == "GGD":
                return self._gpm_aim_distance(arg)
            if code == "GM":
                return self._gpm_landmark_query(arg)
            if code == "GMA":
                return self._gpm_landmark_add(arg)
            if code == "GMN":
                return f"* {len(self.device.gpm_landmarks)}\r\n"
            if code == "GMD":
                return self._gpm_landmark_delete(arg)
            if code == "GMC":
                self.device.gpm_landmarks.clear()
                return self._ok()
        raise ProtocolError(f"Unknown command '{token}'")

    # -- posição/orientação própria: GL/GO/GA/GLLA, GR/GP/GY/GRPY, GCP -------
    # Consulta E definição sempre respondem com o valor atual formatado em
    # 6 casas decimais — diferente do "*\r\n" seco dos comandos de posição
    # de eixo (PP/TP). Confirmado pelo exemplo da seção 17.4.3 do manual.
    def _gpm_single(self, arg: str, field: str) -> str:
        pose = self.device.gpm_pose
        if arg != "":
            setattr(pose, field, self._parse_float(arg))
        return f"* {getattr(pose, field):.6f}\r\n"

    def _gpm_combined(self, arg: str, fields: tuple[str, ...]) -> str:
        pose = self.device.gpm_pose
        if arg != "":
            parts = arg.split(",")
            if len(parts) != len(fields):
                raise ProtocolError(f"Expected {len(fields)} comma-separated values, got '{arg}'")
            for field, part in zip(fields, parts):
                setattr(pose, field, self._parse_float(part))
        values = (getattr(pose, field) for field in fields)
        return "* " + ",".join(f"{value:.6f}" for value in values) + "\r\n"

    # -- aim point: GG (aponta/consulta) e GGD (distância) -------------------
    # GG é uma ação (como PP/TP): ao definir, responde só "*\r\n", sem
    # ecoar o valor — diferente de GLLA/GRPY/GCP. A consulta usa 5 casas
    # decimais (confirmado pelo exemplo "GG * 38.60138,-122.37686,6.00000"
    # da seção 17.5.3, diferente das 6 casas dos comandos da seção 17.4).
    def _gpm_aim(self, arg: str) -> str:
        tracker = self.device.geo_tracker
        if arg == "":
            if tracker.state.target is None:
                raise ProtocolError("No aim point set yet")
            point = tracker.state.target
            return f"* {point.lat_deg:.5f},{point.lon_deg:.5f},{point.alt_m:.5f}\r\n"

        parts = arg.split(",")
        if len(parts) == 1:
            point = self._landmark_point(self._parse_int(parts[0]))
        elif len(parts) == 3:
            lat, lon, alt = (self._parse_float(p) for p in parts)
            point = GeoPoint(lat_deg=lat, lon_deg=lon, alt_m=alt)
        else:
            raise ProtocolError(f"Expected <index> or <lat>,<lon>,<alt>, got '{arg}'")

        tracker.set_target(point)
        return self._ok()

    def _gpm_aim_distance(self, arg: str) -> str:
        """GGD — distância (m) até o aim point atual, ou até um ponto informado.

        Formato de resposta (número de casas decimais) não aparece em
        nenhum exemplo fotografado do manual; usamos 4 casas por
        consistência com o resto do capítulo, mas isso é uma suposição
        deste simulador, não uma confirmação.
        """
        tracker = self.device.geo_tracker
        if arg == "":
            if tracker.state.last_look is None:
                raise ProtocolError("No aim point set yet")
            distance = tracker.state.last_look.range_m
        else:
            parts = arg.split(",")
            if len(parts) != 3:
                raise ProtocolError(f"Expected <lat>,<lon>,<alt>, got '{arg}'")
            lat, lon, alt = (self._parse_float(p) for p in parts)
            target = GeoPoint(lat_deg=lat, lon_deg=lon, alt_m=alt)
            distance = look_angles(tracker.observer(), target).range_m
        return f"* {distance:.4f}\r\n"

    # -- landmarks: GM/GMA/GMN/GMD/GMC ----------------------------------------
    def _gpm_landmark_query(self, arg: str) -> str:
        landmarks = self.device.gpm_landmarks
        if arg == "":
            entries = ";".join(
                self._format_landmark(index, landmark)
                for index, landmark in enumerate(landmarks)
            )
            return f"* {entries}\r\n"
        index = self._parse_int(arg)
        landmark = self._landmark_at(index)
        return f"* {self._format_landmark(index, landmark)}\r\n"

    def _format_landmark(self, index: int, landmark: Landmark) -> str:
        # Campos confirmados: <index>,<name>,<lat>,<lon>,<alt>,<span
        # pos>,<tilt pos>,<error>. O erro de mira não é modelado (o
        # manual não detalha o cálculo) e fica sempre 0.0000.
        return (
            f"{index},{landmark.name},{landmark.lat_deg:.4f},{landmark.lon_deg:.4f},"
            f"{landmark.alt_m:.4f},{landmark.pan_position},{landmark.tilt_position},0.0000"
        )

    def _gpm_landmark_add(self, arg: str) -> str:
        parts = arg.split(",")
        if len(parts) != 4:
            raise ProtocolError(f"Expected <name>,<lat>,<lon>,<alt>, got '{arg}'")
        name, lat_text, lon_text, alt_text = parts
        landmark = Landmark(
            name=name,
            lat_deg=self._parse_float(lat_text),
            lon_deg=self._parse_float(lon_text),
            alt_m=self._parse_float(alt_text),
            pan_position=self.device.pan.position,
            tilt_position=self.device.tilt.position,
        )
        self.device.gpm_landmarks.append(landmark)
        return self._ok()

    def _gpm_landmark_delete(self, arg: str) -> str:
        landmarks = self.device.gpm_landmarks
        if arg == "":
            if landmarks:
                landmarks.pop()
        else:
            index = self._parse_int(arg)
            self._landmark_at(index)  # valida o índice antes de remover
            landmarks.pop(index)
        return self._ok()

    def _landmark_at(self, index: int) -> Landmark:
        landmarks = self.device.gpm_landmarks
        if not 0 <= index < len(landmarks):
            raise ProtocolError(f"Unknown landmark index {index}")
        return landmarks[index]

    def _landmark_point(self, index: int) -> GeoPoint:
        landmark = self._landmark_at(index)
        return GeoPoint(lat_deg=landmark.lat_deg, lon_deg=landmark.lon_deg, alt_m=landmark.alt_m)

    def _set_host_port(self, token: str) -> str:
        """Comando ``@(baud,0,F)``: configura a porta serial do host."""
        match = _BAUD_RE.match(token)
        if not match:
            raise ProtocolError("Expected @(<baud>,0,F)")
        self.device.host_baudrate = int(match.group(1))
        return self._ok()

    def _await_completion(self) -> str:
        self.device.apply_pending_targets()
        start = time.monotonic()
        while self.device.is_in_motion():
            if time.monotonic() - start > self.await_timeout:
                return "! Await timed out\r\n"
            time.sleep(0.01)
        return self._ok()

    # -- save/restore de configurações --------------------------------------
    def _capture_settings(self) -> dict:
        with self.device.lock:
            return {
                axis.spec.name: {
                    "desired_speed": axis.desired_speed,
                    "base_speed": axis.base_speed,
                    "acceleration": axis.acceleration,
                    "upper_speed_limit": axis.upper_speed_limit,
                    "lower_speed_limit": axis.lower_speed_limit,
                    "limit_mode": axis.limit_mode,
                    "step_mode": axis.step_mode,
                    "hold_power": axis.hold_power,
                    "move_power": axis.move_power,
                }
                for axis in self.device.axes
            }

    def _restore_settings(self, saved: dict) -> None:
        with self.device.lock:
            for axis in self.device.axes:
                for key, value in saved[axis.spec.name].items():
                    if key == "step_mode":
                        axis.set_step_mode(value)
                    else:
                        setattr(axis, key, value)

    # -- formatação de respostas ---------------------------------------------
    def _ok(self) -> str:
        return "*\r\n"

    def _value(self, value, phrase: str) -> str:
        if self.device.verbose_feedback:
            return f"* {phrase} {value}\r\n"
        return f"* {value}\r\n"

    def _text(self, value: str, phrase: str) -> str:
        if self.device.verbose_feedback:
            return f"* {phrase} {value}\r\n"
        return f"* {value}\r\n"

    # -- utilitários ----------------------------------------------------------
    def _parse_int(self, text: str) -> int:
        try:
            return int(text)
        except ValueError:
            raise ProtocolError(f"Invalid integer value '{text}'")

    def _parse_float(self, text: str) -> float:
        try:
            return float(text)
        except ValueError:
            raise ProtocolError(f"Invalid decimal value '{text}'")

    def _parse_positive_int(self, text: str) -> int:
        value = self._parse_int(text)
        if value < 0:
            raise ProtocolError(f"Value must not be negative: '{text}'")
        return value

    def _lookup(self, table: dict, letter: str, what: str):
        if letter not in table:
            valid = "/".join(sorted(table))
            raise ProtocolError(f"Unknown {what} '{letter}' (expected {valid})")
        return table[letter]
