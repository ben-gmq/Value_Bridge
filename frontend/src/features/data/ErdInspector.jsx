// The ERD's right-hand panel (D-51, the canvas look of mockup 02): the focused card's keys and
// relationships, or — with nothing focused — what this diagram shows. Read-only; it links out only.
import { Link as RouterLink } from 'react-router-dom';
import { Box, Button, Divider, IconButton, Typography } from '@mui/material';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { links } from '../../app/links';
import { Card, Code, ListRow, SectionLabel, Status, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { cardinalityText } from './ErdParts';
import { entityNodeId, ghostNodeId, splitFields } from './erdModel';

/** A relationship as a row: the entity at the other end, its cardinality and kind; a click focuses it. */
function RelRow({ code, name, rel, onClick }) {
  return (
    <ListRow onClick={onClick} sx={{ py: 1, flexDirection: 'column', alignItems: 'stretch', gap: 0.5 }}>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
        <Code tone="teal" sx={{ fontSize: 12 }}>{code}</Code>
        <Typography sx={{ fontSize: 13.5, flexGrow: 1, minWidth: 0, wordBreak: 'break-word' }}>{name}</Typography>
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
        <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{cardinalityText(rel)}</Typography>
        <Tag tone="neutral" sx={{ height: 20, fontSize: 11 }}>
          {t(rel.identifying ? 'data.erd.table.identifying' : 'data.erd.table.nonIdentifying')}</Tag>
      </Box>
    </ListRow>
  );
}

export function ErdInspector({ g, focusId, onFocus, projectId, scopeName, canEdit }) {
  const close = (
    <IconButton size="small" aria-label={t('data.erd.closeDetails')} onClick={() => onFocus(null)}>
      <CloseRounded fontSize="small" /></IconButton>);
  const entity = focusId && g.entities.find((e) => entityNodeId(e.data_entity_id) === focusId);
  const ghostRef = !entity && focusId && g.outside_refs.find((r) => ghostNodeId(r.parent_data_entity_id) === focusId);

  if (entity || ghostRef) {
    const deId = entity ? entity.data_entity_id : ghostRef.parent_data_entity_id;
    const byId = new Map(g.entities.map((e) => [e.data_entity_id, e]));
    const all = [...g.relationships, ...g.outside_refs];
    const parents = all.filter((r) => r.child_data_entity_id === deId);
    const children = all.filter((r) => r.parent_data_entity_id === deId);
    const keys = entity ? splitFields(entity).keys : [];
    const nodeOf = (id) => (byId.has(id) ? entityNodeId(id) : ghostNodeId(id));
    return (
      <Card title={t('data.erd.inspectTitle')} action={close}>
        <Box>
          <Code tone="teal">{entity ? entity.de_number : ghostRef.parent_de_number}</Code>
          <Typography sx={{ fontSize: 20, fontWeight: 700, mt: 0.5, wordBreak: 'break-word' }}>
            {entity ? entity.de_name : ghostRef.parent_de_name}</Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>
            {entity && <Tag tone="teal">{t('data.erd.fieldCount', { n: entity.fields.length })}</Tag>}
            {ghostRef && <Tag tone="neutral">{t(ghostRef.retired ? 'data.erd.retiredParent' : 'data.erd.outside')}</Tag>}
          </Box>
        </Box>
        {entity && (<>
          <Divider />
          <SectionLabel>{t('data.erd.keys')}</SectionLabel>
          {entity.warnings.includes('NO_KEY') && <Status tone="caution" size="sm">{t('data.erd.noKeyHelp')}</Status>}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
            {keys.map((f) => (
              <Box key={f.data_field_id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {f.is_primary_key && <Tag tone="teal" sx={{ height: 20, fontSize: 11 }}>{t('data.erd.pkShort')}</Tag>}
                {f.is_foreign_key && <Tag tone="navy" sx={{ height: 20, fontSize: 11 }}>{t('data.erd.fkShort')}</Tag>}
                <Typography sx={{ fontSize: 13.5, flexGrow: 1, minWidth: 0, wordBreak: 'break-word' }}>{f.field_name}</Typography>
                {f.is_foreign_key && f.ref_de_name && (
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>{t('data.erd.fkTo', { name: f.ref_de_name })}</Typography>)}
              </Box>))}
          </Box>
        </>)}
        <SectionLabel>{t('data.erd.table.parent')}</SectionLabel>
        {parents.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.erd.relNone')}</Typography>}
        {parents.map((r) => (
          <RelRow key={`p${r.parent_data_entity_id}-${r.fk_group_no}`} rel={r} code={r.parent_de_number} name={r.parent_de_name}
            onClick={() => onFocus(nodeOf(r.parent_data_entity_id))} />))}
        <SectionLabel>{t('data.erd.referredBy')}</SectionLabel>
        {children.length === 0 && <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>{t('data.erd.relNone')}</Typography>}
        {children.map((r) => {
          const c = byId.get(r.child_data_entity_id);
          return (
            <RelRow key={`c${r.child_data_entity_id}-${r.fk_group_no}`} rel={r} code={c?.de_number} name={c?.de_name}
              onClick={() => onFocus(entityNodeId(r.child_data_entity_id))} />);
        })}
        <Button variant="contained" fullWidth component={RouterLink} to={links.entity(projectId, deId)} sx={{ mt: 1 }}>
          {t('data.erd.openEntity')}</Button>
      </Card>
    );
  }

  return (
    <Card title={t('data.erd.summary')}>
      <Box>
        <Typography sx={{ fontSize: 16, fontWeight: 700, wordBreak: 'break-word' }}>{scopeName}</Typography>
        <Typography sx={{ fontSize: 13, color: 'text.secondary', mt: 0.5 }}>
          {t('data.erd.counts', { entities: g.entities.length, relationships: g.relationships.length, stubs: g.outside_refs.length })}
        </Typography>
      </Box>
      <Divider />
      <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>{t(canEdit ? 'data.erd.help' : 'data.erd.helpReadOnly')}</Typography>
    </Card>
  );
}
