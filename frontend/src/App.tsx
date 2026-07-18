// Phase 0 placeholder: exists only to prove the theme tokens and fonts load.
// Phase 9 (Frontend Foundation) replaces this with the real app shell + router.
function App() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-16 p-32">
      <h1 className="text-gradient font-display text-hero font-bold">AgentDesk</h1>
      <p className="text-muted text-body">AI-native ticket management</p>
      <div className="flex gap-8">
        <span className="rounded-pill bg-critical text-body-sm px-12 py-4 font-medium text-white">
          Critical
        </span>
        <span className="rounded-pill bg-high text-body-sm px-12 py-4 font-medium text-white">
          High
        </span>
        <span className="rounded-pill bg-low text-body-sm px-12 py-4 font-medium text-white">
          Low
        </span>
      </div>
      <code className="font-mono text-data text-muted">TKT-0001 · 36 min 47s</code>
    </main>
  )
}

export default App
