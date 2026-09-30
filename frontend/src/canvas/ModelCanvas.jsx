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
      sx={{ height, width: '100%', border: 1, borderColor: 'divider', borderRadius: 1, overflow: 'hidden' }}>
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange}
          onNodeDragStop={onNodeDragStop} onConnect={onConnect} nodesConnectable={connectable}
          onlyRenderVisibleElements colorMode={colorMode} deleteKeyCode={null} fitView minZoom={0.1}>
          <Background gap={24} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </Box>
  );
}
