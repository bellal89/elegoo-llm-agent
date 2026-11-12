from elegoo.protocol import ErrReason


class ElegooError(Exception):
    pass


class LinkError(ElegooError):
    pass


class CommandRejectedError(ElegooError):
    def __init__(self, reason: ErrReason) -> None:
        super().__init__(f"command rejected: {reason}")
        self.reason = reason


class ReplyTimeoutError(ElegooError):
    pass


class ProfileError(ElegooError):
    pass


class CalibrationError(ElegooError):
    pass


class CameraError(ElegooError):
    pass


class ToolCallError(ElegooError):
    pass


class ModelTimeoutError(ElegooError):
    pass


class NotReadyError(ElegooError):
    pass
