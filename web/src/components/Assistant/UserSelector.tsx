import { useState, useEffect } from 'react';
import { User, ChevronDown } from 'lucide-react';

interface UserInfo {
  user_id: string;
  name: string;
  sample_count: number;
}

interface UserSelectorProps {
  selectedUserId: string | null;
  onSelectUser: (userId: string | null) => void;
}

export const UserSelector = ({ selectedUserId, onSelectUser }: UserSelectorProps) => {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetch('/api/users')
      .then((res) => res.json())
      .then((data) => {
        setUsers(data);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load users:', err);
        setIsLoading(false);
      });
  }, []);

  const selectedUser = users.find((u) => u.user_id === selectedUserId);

  const handleSelect = (userId: string | null) => {
    onSelectUser(userId);
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-raised border border-border-subtle hover:bg-surface-hover transition-colors"
        disabled={isLoading}
      >
        <User size={14} className="text-text-muted" />
        <span className="text-sm text-text-primary">
          {isLoading ? 'Loading...' : selectedUser?.name || 'Guest'}
        </span>
        <ChevronDown size={14} className="text-text-muted" />
      </button>

      {isOpen && (
        <>
          {/* Backdrop to close dropdown */}
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />

          {/* Dropdown menu */}
          <div className="absolute top-full mt-1 left-0 w-48 bg-surface-raised border border-border-subtle rounded-lg shadow-lg overflow-hidden z-20">
            <button
              onClick={() => handleSelect(null)}
              className="w-full px-3 py-2 text-left text-sm hover:bg-surface-hover transition-colors text-text-secondary"
            >
              Guest
            </button>
            {users.map((user) => (
              <button
                key={user.user_id}
                onClick={() => handleSelect(user.user_id)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-surface-hover transition-colors flex items-center gap-2"
              >
                <span className="text-text-primary">{user.name}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
