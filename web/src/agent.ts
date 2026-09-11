// The agent's name: what people say to wake it and how the UI refers to it. Served by the worker (MARVIN_NAME).
export const agent = { name: "Marvin" };

export async function loadAgentName(): Promise<string> {
  try {
    const r = await fetch("/api/agent");
    const j = await r.json();
    if (typeof j.name === "string" && j.name) agent.name = j.name;
  } catch {
    /* keep the default */
  }
  return agent.name;
}
