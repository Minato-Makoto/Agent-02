import * as path from 'path';

export function isPathInside(parent: string, child: string): boolean {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative);
}

export function resolveInside(baseDir: string, requestedPath: string): string {
  const target = path.resolve(baseDir, requestedPath);
  if (target === path.resolve(baseDir) || isPathInside(baseDir, target)) {
    return target;
  }

  throw new Error(`Access denied: path "${requestedPath}" is outside the allowed workspace.`);
}
