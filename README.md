# interface

A browser page for a laptop plugged into a mesh node. It shows the node's status, neighbors, routes and the whole network from status broadcasts, and it sends and receives messages. It speaks only the line protocol of `mesh-network/SPEC.md` Section 11, so it works with any node and needs no internet connection.

**Status (27 October 2026):** first version. Tested against the simulator (8 nodes, kill, reroute, plug into another node, text and telemetry delivered); the USB path has not yet run against a board.

## Files

| File | Contents |
|---|---|
| `index.html` | The page: one file, no libraries. Web Serial for USB, a simulator mode, polling of the node's tables, the send form, the console. |
| `serve.py` | Serves the page on localhost (Web Serial needs a secure origin) and, with `--sim`, runs `lmesh_console` and bridges it to the page. Python standard library only. |

## Use with a board

Requires Chrome or Edge (Web Serial). Close any other serial monitor on the port first (PlatformIO, PuTTY).

```
python serve.py
```

Open http://localhost:8000, press **Connect USB**, pick the ST-LINK port (115200 baud). The page asks for `id` and then polls `links`, `routes`, `nodes`, `msgs` and `stats` every 5 s, and sooner after an event.

## Use without a board

Build the simulator console in `mesh-network` (`cmake --build build`), then:

```
python serve.py --sim --speed 10
```

Open http://localhost:8000/?sim. The page connects to node 1 of a simulated network running the real library. The simulator bar can plug into any node, kill and revive nodes, and cut or join links. Options: `--topo line|ring|diamond|random`, `--nodes N`, `--seed S`, `--loss PCT`, `--speed X` (simulated seconds per real second).

## Panels

- **This node:** identity, radio settings from the driver's `radio` event, uptime, neighbor and route counts, store depth, delivery and error counters, frames by type.
- **Network:** a map of every node heard, with links from this node's neighbor table and every status broadcast, colored by ETX; stale nodes are gray.
- **Nodes:** the node table: battery, uptime, store, health flags, last heard, each node's neighbors.
- **Neighbors** and **Routes:** this node's tables.
- **Send** and **Received:** text, command and telemetry messages with their delivery state; messages addressed to this node.
- **Console:** every line the node sends, and a command box for the line protocol.

## Techniques

- **One command in flight.** Commands go through a queue; dump rows are collected until the `end` line, and event lines (`ev`) are handled whenever they arrive, so events and replies never mix up.
- **Node clock estimate.** "Heard" times are node-clock values, so the page keeps the newest event time plus elapsed wall time to show ages.
- **Simulator bridge.** `lmesh_console` reads commands for the attached node and `@` control lines on stdin; `serve.py` sends `@t <ms>` every 50 ms to advance the virtual clock in step with wall time, and forwards output to the page as server-sent events.

## Known gaps

- The node table does not include the node itself, so this node's own battery and health flags are not shown; it needs the library to report its own status, or a firmware `battery` line.
- The map uses a circle layout, which gets busy past about 10 nodes.
