import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/Toast';
import { fetchGroup, addMember, removeMember, searchUsers } from '../api';
import Spinner from '../components/Spinner';
import Modal from '../components/Modal';

export default function GroupDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const toast = useToast();

  const [group, setGroup] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [removingId, setRemovingId] = useState(null);

  const canManage =
    user?.is_admin || (user?.managed_group_ids || []).includes(id);

  const loadGroup = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchGroup(id)
      .then(setGroup)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    loadGroup();
  }, [loadGroup]);

  const handleRemoveMember = async (memberId, memberName) => {
    if (!confirm(`Remove ${memberName || memberId} from this group?`)) return;
    setRemovingId(memberId);
    try {
      await removeMember(id, memberId);
      toast.success('Member removed successfully.');
      loadGroup();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRemovingId(null);
    }
  };

  const handleMemberAdded = () => {
    setAddModalOpen(false);
    loadGroup();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <BackLink />
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mt-4">
          {error}
        </div>
      </div>
    );
  }

  const members = group?.members || [];

  return (
    <div>
      <BackLink />

      {/* Group header */}
      <div className="mt-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{group?.displayName}</h1>
          <p className="mt-1 text-sm text-gray-400 font-mono">Group ID: {group?.id}</p>
        </div>
        {canManage && (
          <button
            onClick={() => setAddModalOpen(true)}
            className="inline-flex items-center px-4 py-2.5 text-sm font-medium text-white bg-db-red hover:bg-db-red-dark rounded-lg transition-colors"
          >
            <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Member
          </button>
        )}
      </div>

      {/* Members table */}
      <div className="mt-6 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">
            Members ({members.length})
          </h2>
        </div>

        {members.length === 0 ? (
          <div className="px-6 py-12 text-center text-gray-400">
            This group has no members yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Display Name
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    User ID
                  </th>
                  {canManage && (
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {members.map((member) => (
                  <tr key={member.value} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {member.display || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                      {member.value}
                    </td>
                    {canManage && (
                      <td className="px-6 py-4 whitespace-nowrap text-right">
                        <button
                          onClick={() => handleRemoveMember(member.value, member.display)}
                          disabled={removingId === member.value}
                          className="text-sm text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
                        >
                          {removingId === member.value ? 'Removing...' : 'Remove'}
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add member modal */}
      <AddMemberModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        groupId={id}
        onAdded={handleMemberAdded}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/" className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
      <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
      </svg>
      Back to Dashboard
    </Link>
  );
}

function AddMemberModal({ open, onClose, groupId, onAdded }) {
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [addingId, setAddingId] = useState(null);

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

  const handleAdd = async (userId, userName) => {
    setAddingId(userId);
    try {
      await addMember(groupId, userId);
      toast.success(`Added ${userName || userId} to the group.`);
      onAdded();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAddingId(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add Member">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Search users
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
              onClick={() => handleAdd(u.id, u.displayName)}
              disabled={addingId === u.id}
              className="ml-3 inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-db-red hover:bg-db-red-dark rounded-md transition-colors disabled:opacity-50"
            >
              {addingId === u.id ? 'Adding...' : 'Add'}
            </button>
          </div>
        ))}
      </div>
    </Modal>
  );
}
