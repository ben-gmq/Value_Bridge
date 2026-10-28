import { useParams, useSearchParams } from 'react-router-dom';
import { Segmented } from '../../components/kit';
import { Page } from '../../components/Page';
import { t } from '../../i18n/t';
import { Traceability } from './Traceability';

// Slice 1f (spec §4): one Reports page, a Segmented choice of the reports (?tab=). Every report is read-only and
// worked out on each read; the screen never adds anything up itself.
const TABS = ['traceability'];

export default function ReportsPage() {
  const { projectId } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get('tab')) ? params.get('tab') : TABS[0];
  return (
    <Page title={t('reports.title')} subtitle={t('reports.subtitle')}>
      <Segmented label={t('reports.title')} value={tab} sx={{ mb: 2 }}
        onChange={(v) => setParams(v === TABS[0] ? {} : { tab: v }, { replace: true })}
        options={TABS.map((v) => ({ value: v, label: t(`reports.tab.${v}`) }))} />
      {tab === 'traceability' && <Traceability projectId={projectId} />}
    </Page>
  );
}
