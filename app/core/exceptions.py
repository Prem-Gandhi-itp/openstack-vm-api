"""
Domain-specific exceptions for clean error propagation
"""


class VMNotFoundError(Exception):
    def __init__(self, vm_id: str):
        self.vm_id = vm_id
        super().__init__(f"VM '{vm_id}' not found.")


class VMOperationError(Exception):
    def __init__(self, operation: str, reason: str):
        self.operation = operation
        self.reason = reason
        super().__init__(f"Operation '{operation}' failed: {reason}")


class InvalidVMStateError(Exception):
    def __init__(self, vm_id: str, current_state: str, required_state: str):
        self.vm_id = vm_id
        self.current_state = current_state
        self.required_state = required_state
        super().__init__(
            f"VM '{vm_id}' is in state '{current_state}', "
            f"but '{required_state}' is required for this operation."
        )


class OpenStackConnectionError(Exception):
    def __init__(self, message: str = "Failed to connect to OpenStack"):
        super().__init__(message)


class SnapshotNotFoundError(Exception):
    def __init__(self, snapshot_id: str):
        self.snapshot_id = snapshot_id
        super().__init__(f"Snapshot '{snapshot_id}' not found.")


class QuotaExceededError(Exception):
    def __init__(self, resource: str):
        self.resource = resource
        super().__init__(f"Quota exceeded for resource: {resource}")


class VMLockedError(Exception):
    def __init__(self, vm_id: str):
        self.vm_id = vm_id
        super().__init__(f"VM '{vm_id}' is locked and cannot be modified.")


class VMAlreadyLockedError(Exception):
    def __init__(self, vm_id: str):
        self.vm_id = vm_id
        super().__init__(f"VM '{vm_id}' is already locked.")


class VMNotLockedError(Exception):
    def __init__(self, vm_id: str):
        self.vm_id = vm_id
        super().__init__(f"VM '{vm_id}' is not locked.")
