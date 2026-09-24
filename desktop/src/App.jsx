import React, { useState } from "react";
import Gate from "./screens/Gate.jsx";
import Workspace from "./components/Workspace.jsx";

export default function App() {
  const [session, setSession] = useState(null); // {username, platform}

  if (!session) {
    return <Gate onReady={setSession} />;
  }
  return (
    <Workspace
      username={session.username}
      platform={session.platform}
      onExit={() => setSession(null)}
    />
  );
}
