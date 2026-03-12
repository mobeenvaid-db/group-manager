import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Header() {
  const { user } = useAuth();
  const location = useLocation();

  const isActive = (path) =>
    location.pathname === path
      ? 'text-white bg-db-navy-light'
      : 'text-gray-300 hover:text-white hover:bg-db-navy-light';

  return (
    <header className="bg-db-navy shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Left: Logo and nav */}
          <div className="flex items-center space-x-6">
            <Link to="/" className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-db-red rounded flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <span className="text-white font-semibold text-lg">Group Manager</span>
            </Link>

            <nav className="flex space-x-1">
              <Link to="/" className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive('/')}`}>
                Dashboard
              </Link>
              {user?.is_admin && (
                <Link to="/admin" className={`px-3 py-2 rounded-md text-sm font-medium transition-colors ${isActive('/admin')}`}>
                  Admin Panel
                </Link>
              )}
            </nav>
          </div>

          {/* Right: User info */}
          <div className="flex items-center space-x-3">
            {user?.is_admin && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-db-red text-white">
                Admin
              </span>
            )}
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-db-slate rounded-full flex items-center justify-center text-white text-sm font-medium">
                {(user?.email || '?')[0].toUpperCase()}
              </div>
              <span className="text-gray-300 text-sm hidden sm:inline">{user?.email}</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
