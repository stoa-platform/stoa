package connect

import "errors"

// ErrGatewayNotFound is returned by Heartbeat when the CP responds 404,
// indicating the gateway instance was purged on the CP side and needs
// re-registration. Consumers compare via errors.Is(err, ErrGatewayNotFound).
var ErrGatewayNotFound = errors.New("gateway not found on Control Plane (purged)")

// ErrNotRegistered is returned by any CP-bound call attempted before the
// agent has completed Register() (or after ClearGatewayID on re-register).
// Consumers compare via errors.Is(err, ErrNotRegistered).
var ErrNotRegistered = errors.New("stoa-connect: agent not registered with Control Plane")
