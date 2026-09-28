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
  clients: () => d(http.get('/api/v1/clients')),
  createClient: (body) => d(http.post('/api/v1/clients', body)),

  projects: () => d(http.get('/api/v1/projects')),
  project: (id) => d(http.get(`/api/v1/projects/${id}`)),
  createProject: (body) => d(http.post('/api/v1/projects', body)),
  updateProject: (id, body) => d(http.patch(`/api/v1/projects/${id}`, body)),
  codes: (projectId, category) => d(http.get(`/api/v1/projects/${projectId}/code-master/${category}`)),

  access: (projectId) => d(http.get(`/api/v1/projects/${projectId}/access`)),
  grant: (projectId, body) => d(http.post(`/api/v1/projects/${projectId}/access`, body)),
  revoke: (grantId) => d(http.delete(`/api/v1/access/${grantId}`)),

  programs: () => d(http.get('/api/v1/programs')),
  program: (id) => d(http.get(`/api/v1/programs/${id}`)),
  programProjects: (id) => d(http.get(`/api/v1/programs/${id}/projects`)),
  createProgram: (body) => d(http.post('/api/v1/programs', body)),
  grantProgram: (id, body) => d(http.post(`/api/v1/programs/${id}/access`, body)),
  moveIntoProgram: (id, body) => d(http.post(`/api/v1/programs/${id}/projects`, body)),
};
