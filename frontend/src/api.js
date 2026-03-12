/**
 * API client for all backend calls.
 * All endpoints are prefixed with /api.
 */

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

// Auth
export const fetchMe = () => request('/api/me');

// Groups
export const fetchGroups = (params = {}) => {
  const qs = new URLSearchParams();
  if (params.q) qs.set('q', params.q);
  if (params.startIndex) qs.set('startIndex', params.startIndex);
  if (params.count) qs.set('count', params.count);
  const query = qs.toString();
  return request(`/api/groups${query ? '?' + query : ''}`);
};

export const fetchGroup = (groupId) => request(`/api/groups/${groupId}`);

// Group Members
export const addMember = (groupId, userId) =>
  request(`/api/groups/${groupId}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId }),
  });

export const removeMember = (groupId, memberId) =>
  request(`/api/groups/${groupId}/members/${memberId}`, {
    method: 'DELETE',
  });

// Group Managers
export const fetchGroupManagers = () => request('/api/group-managers');

export const assignGroupManager = (data) =>
  request('/api/group-managers', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const revokeGroupManager = (assignmentId) =>
  request(`/api/group-managers/${assignmentId}`, {
    method: 'DELETE',
  });

// User Search
export const searchUsers = (q) =>
  request(`/api/users/search?q=${encodeURIComponent(q)}`);
