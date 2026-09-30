// ELK runs off the main thread (§14.6). elk-worker detects the worker scope and installs its
// own message dispatcher, so this file only loads it; layout.js talks to it through elk-api.
// (elk.bundled cannot run inside a worker: its fake-worker fallback is not exported there.)
import 'elkjs/lib/elk-worker.min.js';
