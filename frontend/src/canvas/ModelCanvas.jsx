// The ONE diagram component (§7.14, §14.6, VB law 8): <ModelCanvas kind="flow" | "dfd" | "erd">.
// The kind supplies its node types; this owns the rules every diagram shares — visible-only
// rendering, theme-driven colour mode, no keyboard delete, the attribution left visible.
import { Background, ConnectionLineType, Controls, MiniMap, ReactFlow, ReactFlowProvider } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useMemo } from 'react';
import { Box } from '@mui/material';
import { useColorScheme, useTheme } from '@mui/material/styles';
import { EDGE_TYPES } from './edges';

export function ModelCanvas({ kind, nodes, edges, nodeTypes, edgeTypes, onNodesChange, onNodeDragStop, onConnect,
  onConnectEnd, onReconnectEnd, onNodeClick, onNodeDoubleClick, onPaneClick, onEdgeClick, connectable = false, draggable = true,
  minimap = false, minimapNodeColor, ariaLabel, height = '70vh', children }) {
  const { mode, systemMode } = useColorScheme();
  const colorMode = (mode === 'system' ? systemMode : mode) === 'dark' ? 'dark' : 'light';
  const theme = useTheme();
  // Shared edge types first; a kind may add its own (memoised: a new object each render makes
  // React Flow re-mount every edge).
  const types = useMemo(() => ({ ...EDGE_TYPES, ...edgeTypes }), [edgeTypes]);
  // The line being drawn looks like a flow being drawn, not a stray hairline (Ben, 2026-09-30).
  const drawing = { stroke: theme.vars.palette.primary.main, strokeWidth: 2, strokeDasharray: '6 4' };
  return (
    <Box data-canvas-kind={kind} role="region" aria-label={ariaLabel}
      sx={(th) => ({ height, width: '100%', border: 1, borderColor: 'divider', borderRadius: 1, overflow: 'hidden',
        // Clear cursors and visible connectors (Ben, 2026-09-30): the default grab hand renders
        // poorly on Windows, and 6px handles were too small to find.
        '& .react-flow__pane': { cursor: 'default' },
        '& .react-flow__node': { cursor: draggable ? 'move' : 'pointer' },
        '& .react-flow__edge': { cursor: 'pointer' },
        '& .react-flow__handle': { width: 14, height: 14, cursor: 'crosshair',
          bgcolor: th.vars.palette.primary.main, border: 2, borderColor: th.vars.palette.background.paper,
          transition: 'transform 120ms' },
        '& .react-flow__handle-left:hover, & .react-flow__handle-left.valid': {
          transform: 'translate(-50%, -50%) scale(1.35)' },
        '& .react-flow__handle-right:hover, & .react-flow__handle-right.connectingfrom': {
          transform: 'translate(50%, -50%) scale(1.35)' },
      })}>
      <ReactFlowProvider>
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={types} onNodesChange={onNodesChange}
          nodesDraggable={draggable}
          onNodeDragStop={onNodeDragStop} onConnect={onConnect} onConnectEnd={onConnectEnd}
          onReconnectEnd={onReconnectEnd} onNodeClick={onNodeClick} onNodeDoubleClick={onNodeDoubleClick}
          onPaneClick={onPaneClick} zoomOnDoubleClick={!onNodeDoubleClick} onEdgeClick={onEdgeClick} edgesReconnectable={connectable && Boolean(onReconnectEnd)} reconnectRadius={16}
          connectionLineType={ConnectionLineType.SmoothStep} connectionLineStyle={drawing} nodesConnectable={connectable}
          onlyRenderVisibleElements colorMode={colorMode} deleteKeyCode={null} fitView minZoom={0.1}
          connectionRadius={36}>
          <Background gap={24} />
          <Controls showInteractive={false} />
          {minimap && (
            <MiniMap pannable zoomable nodeColor={minimapNodeColor ?? theme.vars.palette.brand.teal}
              maskColor={theme.vars.palette.action.hover} bgColor={theme.vars.palette.background.paper} />)}
          {/* A kind's own helpers that need the React Flow instance (e.g. search-to-focus). */}
          {children}
        </ReactFlow>
      </ReactFlowProvider>
    </Box>
  );
}
