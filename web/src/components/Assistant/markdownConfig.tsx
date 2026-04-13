import remarkGfm from 'remark-gfm';

export const remarkPlugins = [remarkGfm];

export const markdownComponents = {
  p: (props: React.ComponentProps<'p'>) => <p className="mb-2 last:mb-0" {...props} />,
  ul: (props: React.ComponentProps<'ul'>) => (
    <ul className="list-disc ml-4 mb-2 text-text-secondary" {...props} />
  ),
  ol: (props: React.ComponentProps<'ol'>) => (
    <ol className="list-decimal ml-4 mb-2 text-text-secondary" {...props} />
  ),
  strong: (props: React.ComponentProps<'strong'>) => (
    <strong className="font-semibold text-text-primary" {...props} />
  ),
  a: (props: React.ComponentProps<'a'>) => (
    <a
      className="text-amber-400 underline underline-offset-2 hover:text-amber-300"
      {...props}
    />
  ),
  code: (props: React.ComponentProps<'code'>) => (
    <code
      className="bg-white/5 px-1.5 py-0.5 rounded text-[13px] font-mono text-amber-300/80"
      {...props}
    />
  ),
  pre: (props: React.ComponentProps<'pre'>) => (
    <pre
      className="bg-black/40 border border-border-subtle p-3 rounded-xl overflow-x-auto my-2 font-mono text-[13px] text-text-secondary"
      {...props}
    />
  ),
};
