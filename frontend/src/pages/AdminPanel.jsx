import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import {
  fetchGroups,
  fetchGroupManagers,
  assignGroupManager,
  revokeGroupManager,
  searchUsers,
} from '../api';
import Spinner from '../components/Spinner';
import Modal from '../components/Modal';

export default function AdminPanel() {
  const { user } = useAuth();
  const toast = useToast();

  const [groups, setGroups] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loadingGroups, setLoadingGroups] = useState(true);
  const [loadingAssignments, setLoadingAssignments] = useState(true);
  const [groupSearch, setGroupSearch] = useState('');
  const [groupSearchInput, setGroupSearchInput] = useState('');
  const [revokingId, setRevokingId] = useState(null);

  // Assign modal
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [assignGroup, setAssignGroup] = useState(null);

  // Debounce group search
  useEffect(() => {
    const timer = setTimeout(() => setGroupSearch(groupSearchInput), 300);
    return () => clearTimeout(timer);
  }, [groupSearchInput]);

  const loadGroups = useCallback(() => {
    setLoadingGroups(true);
    fetchGroups({ q: groupSearch || undefined, count: 200 })
      .then((data) => setGroups(data.Resources || []))
      .catch((err) => toast.error(err.message))
      .finally(() => setLoadingGroups(false));
  }, [groupSearch]);

  const loadAssignments = useCallback(() => {
    setLoadingAssignments(true);
    fetchGroupManagers()
      .then(setAssignments)
      .catch((err) => toast.error(err.message))
      .finally(() => setLoadingAssignments(false));
  }, []);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  const handleRevoke = async (id, managerName, groupName) => {
    if (!confirm(`Revoke ${managerName}'s manager role for "${groupName}"?`)) return;
    setRevokingId(id);
    try {
      await revokeGroupManager(id);
      toast.success('Manager assignment revoked.');
      loadAssignments();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRevokingId(null);
    }
  };

  const handleAssigned = () => {
    setAssignModalOpen(false);
    setAssignGroup(null);
    loadAssignments();
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Admin Panel</h1>
        <p className="mt-1 text-sm text-gray-500">
          Assign and revoke group manager roles. Managers can add/remove members in their assigned groups.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Groups list */}
        <div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-900 mb-3">Account Groups</h2>
              <input
                type="text"
                placeholder="Search groups..."
                value={groupSearchInput}
                onChange={(e) => setGroupSearchInput(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-db-red focus:border-db-red outline-none"
              />
            </div>

            <div className="max-h-[600px] overflow-y-auto divide-y divide-gray-100">
              {loadingGroups ? (
                <Spinner className="py-8" />
              ) : groups.length === 0 ? (
                <div className="px-6 py-8 text-center text-gray-400 text-sm">
                  No groups found.
                </div>
              ) : (
                groups.map((group) => {
                  const assignmentCount = assignments.filter(
                    (a) => a.group_id === group.id
                  ).length;
                  return (
                    <div
                      key={group.id}
                      className="flex items-center justify-between px-6 py-3 hover:bg-gray-50"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {group.displayName}
                        </p>
                        <p className="text-xs text-gray-400">
                          {(group.members || []).length} members
                          {assignmentCount > 0 && (
                            <span className="ml-2 text-blue-600">
                              {assignmentCount} manager{assignmentCount !== 1 ? 's' : ''}
                            </span>
                          )}
                        </p>
                      </div>
                      <button
                        onClick={() => {
                          setAssignGroup(group);
                          setAssignModalOpen(true);
                        }}
                        className="ml-3 inline-flex items-center px-3 py-1.5 text-xs font-medium text-db-red border border-db-red hover:bg-red-50 rounded-md transition-colors"
                      >
                        + Assign Manager
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Right: Assignments table */}
        <div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-base font-semibold text-gray-900">
                Manager Assignments ({assignments.length})
              </h2>
            </div>

            {loadingAssignments ? (
              <Spinner className="py-8" />
            ) : assignments.length === 0 ? (
              <div className="px-6 py-12 text-center text-gray-400 text-sm">
                No manager assignments yet. Use the groups list to assign managers.
              </div>
            ) : (
              <div className="max-h-[600px] overflow-y-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Group
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Manager
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                        Assigned
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {assignments.map((a) => (
                      <tr key={a.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm text-gray-900">
                          <div className="font-medium truncate max-w-[140px]" title={a.group_display_name}>
                            {a.group_display_name || a.group_id}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="text-gray-900 truncate max-w-[140px]" title={a.manager_display_name}>
                            {a.manager_display_name || a.manager_email}
                          </div>
                          <div className="text-xs text-gray-400 truncate max-w-[140px]">
                            {a.manager_email}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-500">
                          {a.assigned_at ? (
                            <>
                              <div>{formatDate(a.assigned_at)}</div>
                              <div className="text-gray-400">by {a.assigned_by_email || '—'}</div>
                            </>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() =>
                              handleRevoke(
                                a.id,
                                a.manager_display_name || a.manager_email,
                                a.group_display_name || a.group_id
                              )
                            }
                            disabled={revokingId === a.id}
                            className="text-xs text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
                          >
                            {revokingId === a.id ? 'Revoking...' : 'Revoke'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Assign modal */}
      <AssignManagerModal
        open={assignModalOpen}
        onClose={() => {
          setAssignModalOpen(false);
          setAssignGroup(null);
        }}
        group={assignGroup}
        onAssigned={handleAssigned}
      />
    </div>
  );
}

function AssignManagerModal({ open, onClose, group, onAssigned }) {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [assigningId, setAssigningId] = useState(null);

  // Debounced search
  useEffect(() => {
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(() => {
      setSearching(true);
      searchUsers(query)
        .then((data) => setResults(data.Resources || []))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [query]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery('');
      setResults([]);
    }
  }, [open]);

  const handleAssign = async (user) => {
    setAssigningId(user.id);
    try {
      await assignGroupManager({
        group_id: group.id,
        group_display_name: group.displayName,
        manager_id: user.id,
        manager_email: user.email || user.userName,
        manager_display_name: user.displayName,
      });
      toast.success(`Assigned ${user.displayName} as manager of "${group.displayName}".`);
      onAssigned();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAssigningId(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Assign Group Manager">
      {group && (
        <div className="mb-4 px-3 py-2 bg-gray-50 rounded-lg">
          <p className="text-xs text-gray-500 uppercase font-medium">Group</p>
          <p className="text-sm font-semibold text-gray-900">{group.displayName}</p>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Search for a user to assign as manager
        </label>
        <input
          type="text"
          placeholder="Type a name or email..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-db-red focus:border-db-red outline-none"
          autoFocus
        />
      </div>

      <div className="mt-4 max-h-64 overflow-y-auto">
        {searching && <Spinner className="py-4" />}
        {!searching && query.length >= 2 && results.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-4">No users found.</p>
        )}
        {results.map((u) => (
          <div
            key={u.id}
            className="flex items-center justify-between py-2.5 px-2 hover:bg-gray-50 rounded-lg"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 truncate">{u.displayName}</p>
              <p className="text-xs text-gray-500 truncate">{u.email || u.userName}</p>
            </div>
            <button
              onClick={() => handleAssign(u)}
              disabled={assigningId === u.id}
              className="ml-3 inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-db-red hover:bg-db-red-dark rounded-md transition-colors disabled:opacity-50"
            >
              {assigningId === u.id ? 'Assigning...' : 'Assign'}
            </button>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '-';
  try {
    const d = new Date(dateStr + 'Z');
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return dateStr;
  }
}
