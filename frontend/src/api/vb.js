// One module per resource would come with the slices; the foundation is small enough for one.
import { http } from './client';

const d = (p) => p.then((r) => r.data);

export const api = {
  setupStatus: () => d(http.get('/auth/setup')),
  setup: (body) => d(http.post('/auth/setup', body)),
  login: (body) => d(http.post('/auth/login', body)),
  me: () => d(http.get('/auth/me')),

  users: () => d(http.get('/api/v1/users')),
  createUser: (body) => d(http.post('/api/v1/users', body)),
  deactivateUser: (id) => d(http.patch(`/api/v1/users/${id}/deactivate`)),
  setPlatformAdmin: (id, body) => d(http.patch(`/api/v1/users/${id}/platform-admin`, body)),
  setUserKind: (id, body) => d(http.patch(`/api/v1/users/${id}/kind`, body)),
  accessChangePreview: (id, body) => d(http.post(`/api/v1/users/${id}/access-change-preview`, body)),
  clients: () => d(http.get('/api/v1/clients')),
  createClient: (body) => d(http.post('/api/v1/clients', body)),

  projects: () => d(http.get('/api/v1/projects')),
  project: (id) => d(http.get(`/api/v1/projects/${id}`)),
  createProject: (body) => d(http.post('/api/v1/projects', body)),
  updateProject: (id, body) => d(http.patch(`/api/v1/projects/${id}`, body)),
  projectTemplates: () => d(http.get('/api/v1/project-templates')),
  componentCatalogue: () => d(http.get('/api/v1/project-components')),
  components: (id) => d(http.get(`/api/v1/projects/${id}/components`)),
  setComponents: (id, body) => d(http.put(`/api/v1/projects/${id}/components`, body)),
  setDepth: (id, body) => d(http.put(`/api/v1/projects/${id}/data-model-depth`, body)),
  codes: (projectId, category) => d(http.get(`/api/v1/projects/${projectId}/code-master/${category}`)),

  access: (projectId) => d(http.get(`/api/v1/projects/${projectId}/access`)),
  members: (projectId) => d(http.get(`/api/v1/projects/${projectId}/members`)),
  memberCandidates: (projectId) => d(http.get(`/api/v1/projects/${projectId}/member-candidates`)),
  addMember: (projectId, body) => d(http.post(`/api/v1/projects/${projectId}/members`, body)),
  changeMember: (id, body) => d(http.patch(`/api/v1/project-members/${id}`, body)),
  removeMember: (id, rowVersion) => d(http.delete(`/api/v1/project-members/${id}`, { params: { row_version: rowVersion } })),
  setRestriction: (projectId, body) => d(http.put(`/api/v1/projects/${projectId}/restriction`, body)),

  programs: () => d(http.get('/api/v1/programs')),
  program: (id) => d(http.get(`/api/v1/programs/${id}`)),
  programProjects: (id) => d(http.get(`/api/v1/programs/${id}/projects`)),
  createProgram: (body) => d(http.post('/api/v1/programs', body)),
  moveIntoProgram: (id, body) => d(http.post(`/api/v1/programs/${id}/projects`, body)),
};
