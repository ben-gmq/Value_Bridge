// The ONE diagram component (§7.14, §14.6, VB law 8): <ModelCanvas kind="flow" | "dfd" | "erd">.
// The kind supplies its node types; this owns the rules every diagram shares — visible-only
// rendering, theme-driven colour mode, no keyboard delete, the attribution left visible.
import { Background, BackgroundVariant, ConnectionLineType, Controls, MiniMap, ReactFlow, ReactFlowProvider } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useMemo } from 'react';
import { Box } from '@mui/material';
import { useColorScheme, useTheme } from '@mui/material/styles';
import { RADIUS } from '../theme/brand';
import { EDGE_TYPES } from './edges';

export function ModelCanvas({ kind, nodes, edges, nodeTypes, edgeTypes, onNodesChange, onNodeDragStop, onConnect,
  onConnectEnd, onReconnectEnd, onNodeClick, onNodeDoubleClick, onPaneClick, onEdgeClick, connectable = false, draggable = true,
  minimap = false, minimapNodeColor, ariaLabel, height = '70vh', bare = false, fitViewOptions,
  controlsPosition = 'bottom-left', children }) {
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
      sx={(th) => ({ height, width: '100%', overflow: 'hidden', bgcolor: th.vars.palette.background.paper,
        // D-51: the diagram radius (18). `bare` drops the frame when the canvas fills a kit Card.
        ...(bare ? {} : { border: 1, borderColor: 'divider', borderRadius: `${RADIUS.diagram}px` }),
        '& .react-flow': { '--xy-background-color': 'transparent' },
        // The zoom controls and the minimap as the mockups' floating pills (D-51).
        '& .react-flow__controls': { boxShadow: 'none', borderRadius: `${RADIUS.pill}px`, overflow: 'hidden', p: '3px',
          bgcolor: th.vars.palette.background.paper, border: 1, borderColor: th.vars.palette.divider, display: 'flex', gap: '2px' },
        '& .react-flow__controls-button': { bgcolor: 'transparent', border: 0, borderRadius: `${RADIUS.pill}px`,
          width: 30, height: 30, color: th.vars.palette.text.secondary, fill: th.vars.palette.text.secondary,
          '&:hover': { bgcolor: th.vars.palette.brand.selected } },
        '& .react-flow__minimap': { borderRadius: `${RADIUS.field}px`, overflow: 'hidden', border: 1, borderColor: th.vars.palette.divider },
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
          onlyRenderVisibleElements colorMode={colorMode} deleteKeyCode={null} fitView fitViewOptions={fitViewOptions} minZoom={0.1}
          connectionRadius={36}>
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color={theme.vars.palette.brand.lineStrong} />
          <Controls showInteractive={false} orientation="horizontal" position={controlsPosition} />
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
