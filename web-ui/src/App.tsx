import { ChatPanel } from "./components/chat/chat-panel";

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-br from-slate-100 via-slate-200 to-slate-100 p-4 dark:from-slate-900 dark:via-slate-950 dark:to-slate-900">
      <header className="mx-auto w-full max-w-6xl pb-4 hidden">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">Web Agent Chat</h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              A web UI for the Web Agent API with a ChatGPT-inspired experience.
            </p>
          </div>
        </div>
      </header>
      <main className="flex h-full flex-1 justify-center">
        <div className="mx-auto flex w-full max-w-6xl flex-1">
          <ChatPanel />
        </div>
      </main>
      <footer className="mx-auto w-full pt-4 text-center text-xs text-slate-500 dark:text-slate-400">
        Responses may include citations and tool usage details from the Web Agent backend.
      </footer>
    </div>
  );
}
