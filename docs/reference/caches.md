# Cache Layers

Five cache layers reduce per-hop overhead to approximately 1ms in steady state.

| Layer | Location | Primary benefit |
|-------|----------|----------------|
| C1 Adapter instance cache | SDK in-process | Eliminates module import overhead |
| C2 Routing decision cache | SDK + Registry | Reduces routing query from 5-15ms to <0.5ms |
| C3 Heartbeat cache | Registry in-process | Prevents live polling on every route query |
| C4 Context store | Registry external | Keeps IR payloads lean across pipeline hops |
| C5 Calibration signal buffer | SDK in-process | Prevents blocking the hot path on network I/O |

Full specification: [github.com/synapse-ir/spec/s8-caching.md](https://github.com/synapse-ir/spec/blob/main/s8-caching.md)
