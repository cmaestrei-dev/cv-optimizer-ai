import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { waitForJob, type Job } from "../api/client";

/** Lanza un trabajo en segundo plano y sigue su avance. */
export function useJob() {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  const queryClient = useQueryClient();

  const run = useCallback(async (start: () => Promise<Job>): Promise<Job | null> => {
    setError(null);
    setRunning(true);
    try {
      const first = await start();
      setJob(first);
      const done = await waitForJob(first.id, setJob);
      setJob(done);
      return done;
    } catch (e) {
      setError(e);
      return null;
    } finally {
      setRunning(false);
      queryClient.invalidateQueries({ queryKey: ["usage"] }); // los trabajos usan la IA
    }
  }, [queryClient]);

  const reset = useCallback(() => {
    setJob(null);
    setError(null);
  }, []);

  return { job, error, running, run, reset };
}
