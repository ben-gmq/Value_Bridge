import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Avatar, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl,
  InputLabel, MenuItem, Select, Snackbar, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField,
  Typography } from '@mui/material';
import PersonAddAltOutlinedIcon from '@mui/icons-material/PersonAddAltOutlined';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { useAuth } from '../../app/AuthContext';
import { keys } from '../../app/links';
import { useCanAdmin } from '../../app/useCanEdit';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Code, KV, SectionLabel, Status, Tag } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';

// A viewer is offered read only: the server refuses anything higher (D-71 (7)). A stored higher level from before
// that rule is still shown, so the select never goes blank.
const levelsFor = (kind, current) => (kind === 'VIEWER'
  ? ['VIEW', ...(current && current !== 'VIEW' ? [current] : [])] : ['ADMIN', 'EDIT', 'VIEW']);

function LevelSelect({ id, value, onChange, kind }) {
  return (
    <FormControl size="small" sx={{ minWidth: 160 }}>
      <InputLabel id={`${id}-label`}>{t('access.level')}</InputLabel>
      <Select labelId={`${id}-label`} id={id} label={t('access.level')} value={value} onChange={(e) => onChange(e.target.value)}>
        {levelsFor(kind, value).map((l) => (
          <MenuItem key={l} value={l} disabled={kind === 'VIEWER' && l !== 'VIEW'}>{t(`access.level.${l}`)}</MenuItem>))}
      </Select>
    </FormControl>
  );
}

function AddMember({ projectId, onDone }) {
  const users = useQuery({ queryKey: keys.memberCandidates(projectId), queryFn: () => api.memberCandidates(projectId) });
  const [user, setUser] = useState(null);
  const [level, setLevel] = useState('EDIT');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const pick = (u) => { setUser(u); if (u?.user_kind === 'VIEWER') setLevel('VIEW'); };
  const m = useMutation({
    mutationFn: () => api.addMember(projectId, { user_id: user.user_id, access_level: level, member_note: note || null }),
    onSuccess: () => { setUser(null); setNote(''); setError(''); onDone(t('access.added')); },
    onError: (err) => setError(errorText(err, t('access.failed'))),
  });
  return (
    <>
      {error && <Alert severity="error" sx={{ mx: 2.5 }}>{error}</Alert>}
      <Stack direction="row" useFlexGap sx={{ px: 2.5, gap: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>
        <Autocomplete id="member-user" sx={{ flex: '1 1 260px', minWidth: 0 }} value={user} onChange={(_, v) => pick(v)}
          options={users.data ?? []} isOptionEqualToValue={(a, b) => a.user_id === b.user_id}
          getOptionLabel={(u) => `${u.display_name} — ${t(`access.kind.${u.user_kind}`)}`}
          renderInput={(params) => <TextField {...params} size="small" label={t('access.person')} />} />
        <LevelSelect id="member-level" value={level} onChange={setLevel} kind={user?.user_kind} />
        <TextField id="member-note" size="small" label={t('access.note')} value={note} onChange={(e) => setNote(e.target.value)}
          sx={{ flex: '1 1 160px' }} />
        <Button variant="contained" startIcon={<PersonAddAltOutlinedIcon />} disabled={!user || m.isPending}
          onClick={() => m.mutate()}>{t('access.addMember')}</Button>
      </Stack>
      {user?.user_kind === 'VIEWER' && (
        <Typography sx={{ px: 2.5, fontSize: 12.5, color: 'brand.muted' }}>{t('access.viewerOnlyView')}</Typography>)}
    </>
  );
}

const initials = (name = '') => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

// Mockup 10's three explainer tiles, on our levels: administrators (purple, with their names), can edit, read only.
function LevelTile({ title, body, names, strong }) {
  return (
    <Box sx={(th) => ({ p: 2, borderRadius: '24px', minWidth: 0, bgcolor: strong ? th.vars.palette.brand.ftc : th.vars.palette.background.paper,
      border: strong ? 0 : `1px solid ${th.vars.palette.divider}` })}>
      <Typography sx={(th) => ({ fontSize: 12.5, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
        color: strong ? th.vars.palette.brand.onFtcTile : th.vars.palette.brand.muted })}>{title}</Typography>
      <Typography sx={(th) => ({ fontSize: 13.5, mt: 0.5, color: strong ? th.vars.palette.brand.onFtc : th.vars.palette.text.secondary })}>{body}</Typography>
      {names && <Typography sx={(th) => ({ fontSize: 12.5, mt: 1, color: th.vars.palette.brand.onFtcTile, wordBreak: 'break-word' })}>{names}</Typography>}
    </Box>
  );
}

// Who can open the project (D-40, OR-6). Admin only: members, the restriction switch with a
// preview of who loses, gains and keeps access (DR7-D2), and the effective list.
export default function AccessPage() {
  const { projectId } = useParams();
  const { isAdmin } = useAuth();
  const canAdmin = useCanAdmin();
  const qc = useQueryClient();
  const acc = useQuery({ queryKey: keys.projectAccess(projectId), queryFn: () => api.access(projectId), enabled: canAdmin });
  const proj = useQuery({ queryKey: keys.project(projectId), queryFn: () => api.project(projectId) });
  const [preview, setPreview] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const created = Boolean(useLocation().state?.created);       // DR10c-P3: arrived here from "Create project"
  const refresh = () => { qc.invalidateQueries({ queryKey: keys.projectAccess(projectId) });
    qc.invalidateQueries({ queryKey: keys.memberCandidates(projectId) });
    qc.invalidateQueries({ queryKey: keys.project(projectId) }); };
  const fail = (err) => setError(errorText(err, t('access.failed')));

  const restrict = useMutation({
    mutationFn: ({ value, hash }) => api.setRestriction(projectId, { is_restricted: value, confirm_hash: hash ?? null }),
    onSuccess: (res) => { setError('');
      if (res.applied) { setPreview(null); setNotice(t('access.applied')); refresh(); } else setPreview(res); },
    onError: (err) => { setPreview(null); fail(err); },
  });
  const change = useMutation({
    mutationFn: ({ row, level }) => api.changeMember(row.project_member_id, { access_level: level, row_version: row.row_version }),
    onSuccess: () => { setNotice(t('access.changed')); refresh(); }, onError: fail,
  });
  const remove = useMutation({
    mutationFn: (row) => api.removeMember(row.project_member_id, row.row_version),
    onSuccess: () => { setConfirmRemove(null); setNotice(t('access.removed')); refresh(); },
    onError: (err) => { setConfirmRemove(null); fail(err); },
  });

  if (!canAdmin) {
    return <Page title={t('access.title')}><Alert severity="info">{t('access.adminOnly')}</Alert></Page>;
  }
  const data = acc.data;
  const names = (list) => list.map((p) => p.display_name).join(', ');
  return (
    <Page title={t('access.title')} subtitle={t('access.subtitle')} error={error || (acc.error && errorText(acc.error))}
      actions={data && isAdmin && (
        <Button variant="contained" color="warning" disabled={restrict.isPending}
          onClick={() => restrict.mutate({ value: !data.is_restricted })}>
          {data.is_restricted ? t('access.unrestrict') : t('access.restrict')}</Button>)}>
      {created && data?.is_restricted && data.members.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>{t('access.createdNote')}</Alert>)}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: '400px minmax(0, 1fr)' }, alignItems: 'start' }}>
        <Card title={t('settings.acc.project')} bodySx={{ gap: 1.25 }}>
          {proj.data && (
            <>
              <KV k={t('admin.projectName')} v={proj.data.project_name} />
              <KV k={t('project.code')} v={<Code>{proj.data.project_code}</Code>} />
              {proj.data.start_date && <KV k={t('project.start')} v={proj.data.start_date} mono />}
              {proj.data.end_date && <KV k={t('project.end')} v={proj.data.end_date} mono />}
            </>
          )}
          {data && (
            <>
              <SectionLabel sx={{ mt: 1 }}>{t('admin.restricted')}</SectionLabel>
              <Status tone={data.is_restricted ? 'ok' : 'caution'} size="sm">
                {data.is_restricted ? t('settings.acc.restricted') : t('settings.acc.open')}</Status>
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
                {data.is_restricted ? t('access.restricted')
                  : t('access.unrestricted', { users: data.staff?.USER ?? 0, viewers: data.staff?.VIEWER ?? 0 })}
              </Typography>
              {!isAdmin && <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>{t('access.restrictFtcOnly')}</Typography>}
            </>
          )}
        </Card>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Card title={t('access.members')} bodySx={{ px: 0, gap: 1.5 }}
            action={data && <Tag tone="neutral">{t('settings.acc.people', { n: data.members.length })}</Tag>}>
            <Typography sx={{ px: 2.5, fontSize: 13, color: 'text.secondary' }}>{t('access.membersNote')}</Typography>
            <AddMember projectId={projectId} onDone={(msg) => { setNotice(msg); refresh(); }} />
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ pl: 2.5 }}>{t('access.person')}</TableCell>
                    <TableCell>{t('access.level')}</TableCell>
                    <TableCell>{t('access.effective')}</TableCell>
                    <TableCell>{t('access.note')}</TableCell>
                    <TableCell sx={{ pr: 2.5 }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data?.members ?? []).map((row) => (
                    <TableRow key={row.project_member_id}>
                      <TableCell sx={{ pl: 2.5, minWidth: 200 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                          <Avatar sx={(th) => ({ width: 32, height: 32, fontSize: 12, fontWeight: 700, bgcolor: th.vars.palette.background.subtle,
                            color: th.vars.palette.text.secondary })}>{initials(row.display_name)}</Avatar>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography sx={{ fontSize: 14, fontWeight: 600, wordBreak: 'break-word' }}>{row.display_name}</Typography>
                            <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>{t(`access.kind.${row.user_kind}`)}</Typography>
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <LevelSelect id={`lvl-${row.project_member_id}`} value={row.access_level} kind={row.user_kind}
                          onChange={(level) => change.mutate({ row, level })} />
                      </TableCell>
                      <TableCell>
                        <Tag tone={row.effective_level === 'VIEW' ? 'neutral' : 'navy'}>{t(`access.level.${row.effective_level}`)}</Tag>
                        {row.via === 'STAFF' && (
                          <Typography component="span" sx={{ ml: 1, fontSize: 12.5, color: 'brand.muted' }}>{t('access.viaStaff')}</Typography>)}
                      </TableCell>
                      <TableCell sx={{ color: 'text.secondary', wordBreak: 'break-word', minWidth: 120 }}>{row.member_note}</TableCell>
                      <TableCell align="right" sx={{ pr: 2.5 }}>
                        <Button size="small" color="warning" onClick={() => setConfirmRemove(row)}>{t('access.remove')}</Button>
                      </TableCell>
                    </TableRow>))}
                  {data && data.members.length === 0 && (
                    <TableRow><TableCell colSpan={5} sx={{ pl: 2.5, color: 'text.secondary' }}>{t('access.noMembers')}</TableCell></TableRow>)}
                </TableBody>
              </Table>
            </Box>
          </Card>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'repeat(3, minmax(0, 1fr))' } }}>
            <LevelTile strong title={t('access.admins')} body={t('settings.acc.adminWhat')} names={names(data?.admins ?? [])} />
            <LevelTile title={t('access.level.EDIT')} body={t('settings.acc.editWhat')} />
            <LevelTile title={t('access.level.VIEW')} body={t('settings.acc.viewWhat')} />
          </Box>
        </Stack>
      </Box>

      <Dialog open={Boolean(preview)} onClose={() => setPreview(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{preview?.restricted ? t('access.restrictTitle') : t('access.unrestrictTitle')}</DialogTitle>
        <DialogContent>
          {preview && (
            <Stack spacing={1}>
              {preview.loses.length > 0 && <Alert severity="warning">{t('access.loses', { list: names(preview.loses) })}</Alert>}
              {preview.gains.length > 0 && <Typography>{t('access.gains', { list: names(preview.gains) })}</Typography>}
              {preview.restricted && (
                <>
                  <Typography sx={{ fontWeight: 600 }}>{t('access.keeps')}</Typography>
                  {preview.keeps.length === 0 && <Typography sx={{ color: 'text.secondary' }}>{t('access.noMembers')}</Typography>}
                  {preview.keeps.map((k) => (
                    <Box key={k.project_member_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Typography variant="body2">
                        {k.display_name} — {t(`access.level.${k.effective_level}`)}{k.member_note ? ` · ${k.member_note}` : ''}
                      </Typography>
                      {/* DR10c-S1: the server flags a kept member who can edit today and only read once restricted */}
                      {k.level_drops && <Tag tone="caution">{t('access.levelDrops')}</Tag>}
                    </Box>))}
                  {preview.keeps.some((k) => k.level_drops) && (
                    <Alert severity="warning">{t('access.levelDropsNote')}</Alert>)}
                </>
              )}
              {!preview.changed && <Typography>{t('access.nobody')}</Typography>}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPreview(null)}>{t('common.cancel')}</Button>
          <Button variant="contained" color="warning" disabled={restrict.isPending || !preview?.changed}
            onClick={() => restrict.mutate({ value: preview.restricted, hash: preview.confirm_hash })}>{t('access.apply')}</Button>
        </DialogActions>
      </Dialog>
      <ConfirmDialog open={Boolean(confirmRemove)} title={t('access.removeTitle')}
        body={t(data?.is_restricted ? 'access.removeBody' : 'access.removeBodyOpen', { name: confirmRemove?.display_name })}
        confirmLabel={t('access.remove')}
        busy={remove.isPending} onClose={() => setConfirmRemove(null)} onConfirm={() => remove.mutate(confirmRemove)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice('')} message={notice} />
    </Page>
  );
}
