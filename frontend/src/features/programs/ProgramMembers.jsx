import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Autocomplete, Button, Snackbar, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField,
  Typography } from '@mui/material';
import { api } from '../../api/vb';
import { errorText } from '../../api/client';
import { keys } from '../../app/links';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Card, Tag } from '../../components/kit';
import { t } from '../../i18n/t';
import { LevelSelect } from '../projects/AccessPage';

// D-71: a program's members open every live project in it at their level, restricted ones included. Shown only to the
// program's admins and platform admins (the server refuses everyone else). A switched-off user's membership stays
// listed, marked, so it can be removed (design-auditor L1).
export default function ProgramMembers({ programId }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: keys.programMembers(programId), queryFn: () => api.programMembers(programId) });
  const people = useQuery({ queryKey: keys.programMemberCandidates(programId),
    queryFn: () => api.programMemberCandidates(programId) });
  const [user, setUser] = useState(null);
  const [level, setLevel] = useState('EDIT');
  const [confirm, setConfirm] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const refresh = (msg) => { setError(''); setNotice(msg);
    qc.invalidateQueries({ queryKey: keys.programMembers(programId) });
    qc.invalidateQueries({ queryKey: keys.programMemberCandidates(programId) }); };
  const fail = (err) => setError(errorText(err, t('access.failed')));
  const add = useMutation({ mutationFn: () => api.addProgramMember(programId, { user_id: user.user_id, access_level: level }),
    onSuccess: () => { setUser(null); refresh(t('access.added')); }, onError: fail });
  const change = useMutation({ mutationFn: ({ row, lv }) => api.changeProgramMember(row.program_member_id,
    { access_level: lv, row_version: row.row_version }), onSuccess: () => refresh(t('access.changed')), onError: fail });
  const remove = useMutation({ mutationFn: (row) => api.removeProgramMember(row.program_member_id, row.row_version),
    onSuccess: () => { setConfirm(null); refresh(t('access.removed')); }, onError: (err) => { setConfirm(null); fail(err); } });
  const pick = (u) => { setUser(u); if (u?.user_kind === 'VIEWER') setLevel('VIEW'); };

  return (
    <Card title={t('program.members')} bodySx={{ px: 0, gap: 1.5 }}
      action={list.data && <Tag tone="neutral">{t('settings.acc.people', { n: list.data.length })}</Tag>}>
      <Typography sx={{ px: 2.5, fontSize: 13, color: 'text.secondary' }}>{t('program.membersNote')}</Typography>
      {(error || list.error || people.error) && (
        <Alert severity="error" sx={{ mx: 2.5 }}>{error || errorText(list.error || people.error)}</Alert>)}
      <Stack direction="row" useFlexGap sx={{ px: 2.5, gap: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>
        <Autocomplete id="program-member-user" sx={{ flex: '1 1 260px', minWidth: 0 }} value={user} onChange={(_, v) => pick(v)}
          options={people.data ?? []} isOptionEqualToValue={(a, b) => a.user_id === b.user_id}
          getOptionLabel={(u) => `${u.display_name} — ${t(`access.kind.${u.user_kind}`)}`}
          renderInput={(params) => <TextField {...params} size="small" label={t('access.person')} />} />
        <LevelSelect id="program-member-level" value={level} onChange={setLevel} kind={user?.user_kind} />
        <Button variant="contained" disabled={!user || add.isPending} onClick={() => add.mutate()}>{t('access.addMember')}</Button>
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ pl: 2.5 }}>{t('access.person')}</TableCell>
            <TableCell>{t('access.level')}</TableCell>
            <TableCell>{t('access.effective')}</TableCell>
            <TableCell sx={{ pr: 2.5 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {(list.data ?? []).map((row) => (
            <TableRow key={row.program_member_id}>
              <TableCell sx={{ pl: 2.5 }}>
                <Typography sx={{ fontSize: 14, fontWeight: 600 }}>{row.display_name}</Typography>
                <Typography sx={{ fontSize: 12.5, color: 'brand.muted' }}>
                  {t(`access.kind.${row.user_kind}`)}{!row.user_is_active && ` · ${t('program.userOff')}`}</Typography>
              </TableCell>
              <TableCell>
                <LevelSelect id={`plvl-${row.program_member_id}`} value={row.access_level} kind={row.user_kind}
                  onChange={(lv) => change.mutate({ row, lv })} />
              </TableCell>
              <TableCell><Tag tone={row.effective_level === 'VIEW' ? 'neutral' : 'navy'}>{t(`access.level.${row.effective_level}`)}</Tag></TableCell>
              <TableCell align="right" sx={{ pr: 2.5 }}>
                <Button size="small" color="warning" onClick={() => setConfirm(row)}>{t('access.remove')}</Button>
              </TableCell>
            </TableRow>))}
          {list.data && list.data.length === 0 && (
            <TableRow><TableCell colSpan={4} sx={{ pl: 2.5, color: 'text.secondary' }}>{t('access.noMembers')}</TableCell></TableRow>)}
        </TableBody>
      </Table>
      <ConfirmDialog open={Boolean(confirm)} title={t('access.removeTitle')}
        body={t('program.removeBody', { name: confirm?.display_name })} confirmLabel={t('access.remove')}
        busy={remove.isPending} onClose={() => setConfirm(null)} onConfirm={() => remove.mutate(confirm)} />
      <Snackbar open={Boolean(notice)} autoHideDuration={4000} onClose={() => setNotice('')} message={notice} />
    </Card>
  );
}
