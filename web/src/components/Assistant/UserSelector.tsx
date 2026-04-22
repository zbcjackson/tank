import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronUp, Check } from 'lucide-react';

interface UserInfo {
  user_id: string;
  name: string;
  sample_count: number;
}

interface UserSelectorProps {
  selectedUserId: string | null;
  onSelectUser: (userId: string | null) => void;
}

const dropdownVariants = {
  hidden: { opacity: 0, y: 4, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 4, scale: 0.97 },
};

export const UserSelector = ({ selectedUserId, onSelectUser }: UserSelectorProps) => {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const selectedUser = users.find((u) => u.user_id === selectedUserId);
  const displayName = isLoading ? '...' : selectedUser?.name || 'Guest';
  const initials = displayName === '...' ? '' : displayName.charAt(0).toUpperCase();

  const handleSelect = (userId: string | null) => {
    onSelectUser(userId);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={isLoading}
        className="group flex items-center gap-1.5 h-9 pl-1.5 pr-2.5 rounded-xl border border-border-subtle hover:border-amber-500/15 bg-surface-raised transition-all duration-200"
      >
        <span className="w-6 h-6 rounded-lg bg-amber-500/10 border border-amber-500/15 flex items-center justify-center text-[10px] font-semibold text-amber-500/80 tracking-tight shrink-0">
          {initials}
        </span>
        <span className="text-[12px] text-text-secondary group-hover:text-text-primary transition-colors max-w-[60px] truncate">
          {displayName}
        </span>
        <ChevronUp
          size={11}
          className={`text-text-muted transition-transform duration-200 ${isOpen ? '' : 'rotate-180'}`}
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            variants={dropdownVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            transition={{ duration: 0.15, ease: [0.23, 1, 0.32, 1] }}
            className="absolute bottom-full mb-2 left-0 min-w-[180px] py-1.5 bg-surface-overlay border border-border-subtle rounded-xl shadow-[0_8px_32px_rgba(0,0,0,0.5)] z-20 backdrop-blur-sm"
          >
            <div className="px-3 pt-1 pb-2">
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
                Speaking as
              </span>
            </div>
            <button
              onClick={() => handleSelect(null)}
              className="w-full px-3 py-2 text-left text-[13px] hover:bg-white/[0.04] transition-colors flex items-center justify-between group/item"
            >
              <span className="text-text-secondary group-hover/item:text-text-primary transition-colors">
                Guest
              </span>
              {selectedUserId === null && (
                <Check size={13} className="text-amber-500/70" />
              )}
            </button>
            {users.map((user) => (
              <button
                key={user.user_id}
                onClick={() => handleSelect(user.user_id)}
                className="w-full px-3 py-2 text-left text-[13px] hover:bg-white/[0.04] transition-colors flex items-center justify-between group/item"
              >
                <span className="text-text-primary group-hover/item:text-text-primary transition-colors">
                  {user.name}
                </span>
                {selectedUserId === user.user_id && (
                  <Check size={13} className="text-amber-500/70" />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
