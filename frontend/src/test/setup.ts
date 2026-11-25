import { vi } from 'vitest';

// Node provides navigator with the system language; tests must not depend on the machine they run on
vi.stubGlobal('navigator', { language: '', languages: [] });
