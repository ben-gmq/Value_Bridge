// The ONE diagram component (§7.14, §14.6, VB law 8): <ModelCanvas kind="flow" | "dfd" | "erd">.
// The kind supplies its node types; this owns the rules every diagram shares — visible-only
// rendering, theme-driven colour mode, no keyboard delete, the attribution left visible.
import { Background, Controls, ReactFlow, ReactFlowProvider } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Box } from '@mui/material';
import { useColorScheme } from '@mui/material/styles';

export function ModelCanvas({ kind, nodes, edges, nodeTypes, onNodesChange, onNodeDragStop, onConnect,
  connectable = false, ariaLabel, height = '70vh' }) {
  const { mode, systemMode } = useColorScheme();
  const colorMode = (mode === 'system' ? systemMode : mode) === 'dark' ? 'dark' : 'light';
  return (
    <Box data-canvas-kind={kind} role="region" aria-label={ariaLabel}
      sx={(th) => ({ height, width: '100%', border: 1, borderColor: 'divider', borderRadius: 1, overflow: 'hidden',
        // Clear cursors and visible connectors (Ben, 2026-09-30): the default grab hand renders
        // poorly on Windows, and 6px handles were too small to find.
        '& .react-flow__pane': { cursor: 'default' },
        '& .react-flow__node': { cursor: 'move' },
        '& .react-flow__handle': { width: 14, height: 14, cursor: 'crosshair',
          bgcolor: th.vars.palette.primary.main, border: 2, borderColor: th.vars.palette.background.paper,
          transition: 'transform 120ms' },
        '& .react-flow__handle-left:hover, & .react-flow__handle-left.valid': {
          transform: 'translate(-50%, -50%) scale(1.35)' },
        '& .react-flow__handle-right:hover, & .react-flow__handle-right.connectingfrom': {
          transform: 'translate(50%, -50%) scale(1.35)' },
      })}>
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
          onNodeDragStop={onNodeDragStop} onConnect={onConnect} nodesConnectable={connectable}
          onlyRenderVisibleElements colorMode={colorMode} deleteKeyCode={null} fitView minZoom={0.1}
          connectionRadius={36}>
          <Background gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </Box>
  );
}
