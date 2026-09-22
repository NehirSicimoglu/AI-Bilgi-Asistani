import { useState } from 'react'
import { AppShell, type Tab } from './components/AppShell'

function App() {
  const [tab, setTab] = useState<Tab>('chat')
  return <AppShell tab={tab} onNavigate={setTab} />
}

export default App
