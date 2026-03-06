import { execFileSync } from 'child_process';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseWindowsNetstat(output: string, port: number): number[] {
  const pids = new Set<number>();
  const lines = output.split(/\r?\n/);

  for (const line of lines) {
    if (!line.includes('LISTENING')) {
      continue;
    }

    const parts = line.trim().split(/\s+/);
    if (parts.length < 5) {
      continue;
    }

    const localAddress = parts[1] || '';
    const pid = Number(parts[4]);
    if (localAddress.endsWith(`:${port}`) && Number.isInteger(pid) && pid > 0) {
      pids.add(pid);
    }
  }

  return [...pids];
}

function parseUnixLsof(output: string): number[] {
  return [...new Set(
    output
      .split(/\r?\n/)
      .map((line) => Number(line.trim()))
      .filter((pid) => Number.isInteger(pid) && pid > 0),
  )];
}

export function findListeningPids(port: number): number[] {
  try {
    if (process.platform === 'win32') {
      const output = execFileSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8' });
      return parseWindowsNetstat(output, port);
    }

    const output = execFileSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' });
    return parseUnixLsof(output);
  } catch {
    return [];
  }
}

function killPidTree(pid: number): void {
  if (!pid || pid === process.pid) {
    return;
  }

  try {
    if (process.platform === 'win32') {
      execFileSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
      return;
    }

    process.kill(pid, 'SIGTERM');
  } catch {
    // Ignore failures; the caller will verify port state afterwards.
  }
}

export async function freePortIfOccupied(port: number): Promise<number[]> {
  const victims = findListeningPids(port).filter((pid) => pid !== process.pid);
  if (victims.length === 0) {
    return [];
  }

  for (const pid of victims) {
    killPidTree(pid);
  }

  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    if (findListeningPids(port).filter((pid) => pid !== process.pid).length === 0) {
      return victims;
    }
    await sleep(150);
  }

  const remaining = findListeningPids(port).filter((pid) => pid !== process.pid);
  if (remaining.length > 0) {
    throw new Error(`Port ${port} is still busy after attempting to stop process(es): ${remaining.join(', ')}`);
  }

  return victims;
}
