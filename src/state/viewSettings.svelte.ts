const DEFAULT_BOARD_TILT = 8;
const DEFAULT_BOARD_PERSPECTIVE = 1250;
const DEFAULT_BOARD_SCALE_Y = 94;
const DEFAULT_BOARD_LIFT = 0;

export type ResolvedTheme = 'light' | 'dark';
export type ThemePreference = ResolvedTheme | 'system';

const THEME_STORAGE_KEY = 'cabt.theme';
const THEME_QUERY = '(prefers-color-scheme: dark)';
const SETTINGS_STORAGE_KEY = 'cabt.viewSettings';

// Toolbar toggles that survive a reload so testers do not re-check them every session.
type PersistedSettings = {
  followActive?: boolean;
  autoConfirmPrompts?: boolean;
  showLogs?: boolean;
  animateActions?: boolean;
  showActionSpotlight?: boolean;
  revealHands?: boolean;
  sortHand?: boolean;
  showMiniLog?: boolean;
  skin?: string;
  actionStepDelayMs?: number;
};

function readStoredSettings(): PersistedSettings {
  if (typeof window === 'undefined') {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return typeof parsed === 'object' && parsed !== null ? (parsed as PersistedSettings) : {};
  } catch {
    return {};
  }
}

const storedSettings = readStoredSettings();

function storedBoolean(value: boolean | undefined, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function storedDelay(value: number | undefined, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.min(2500, Math.max(50, value)) : fallback;
}

function isResolvedTheme(theme: string | null): theme is ResolvedTheme {
  return theme === 'light' || theme === 'dark';
}

// Dark ("Obsidian Arena") is the default look; users can still pick light/system.
const DEFAULT_THEME_PREFERENCE: ThemePreference = 'dark';

function normalizeThemePreference(theme: string | null): ThemePreference {
  return theme === 'system' || isResolvedTheme(theme) ? theme : DEFAULT_THEME_PREFERENCE;
}

function readStoredThemePreference(): ThemePreference {
  if (typeof window === 'undefined') {
    return DEFAULT_THEME_PREFERENCE;
  }
  try {
    return normalizeThemePreference(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

function readSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'light';
  }
  return window.matchMedia(THEME_QUERY).matches ? 'dark' : 'light';
}

class ViewSettingsStore {
  followActive = $state(storedBoolean(storedSettings.followActive, true));
  autoConfirmPrompts = $state(storedBoolean(storedSettings.autoConfirmPrompts, true));
  debugZones = $state(false);
  showLogs = $state(storedBoolean(storedSettings.showLogs, false));
  // 既定でオン: 相手(AI)の手を1手ずつ再生して見せる。
  animateActions = $state(storedBoolean(storedSettings.animateActions, true));
  // アクションのスポットライト表示（発動カードのポップ）。オフで非表示にできる。
  showActionSpotlight = $state(storedBoolean(storedSettings.showActionSpotlight, true));
  // デバッグ用: 非公開の手札（AI側など）も表向きで表示する。
  revealHands = $state(storedBoolean(storedSettings.revealHands, false));
  // 自分の手札の表示をポケモン→トレーナーズ→エネルギーの順に整列する（表示のみ）。
  sortHand = $state(storedBoolean(storedSettings.sortHand, false));
  // 直近3件だけのミニログ（全ログパネルが閉じている時に表示）。
  showMiniLog = $state(storedBoolean(storedSettings.showMiniLog, true));
  // 見た目スキン（見た目のみの切替。default / tabletop / broadcast / binder）
  skin = $state(typeof storedSettings.skin === 'string' ? storedSettings.skin : 'default');
  actionStepDelayMs = $state(storedDelay(storedSettings.actionStepDelayMs, 650));
  viewIndex = $state(0);
  boardTilt = $state(DEFAULT_BOARD_TILT);
  boardPerspective = $state(DEFAULT_BOARD_PERSPECTIVE);
  boardScaleY = $state(DEFAULT_BOARD_SCALE_Y);
  boardLift = $state(DEFAULT_BOARD_LIFT);
  _themePreference = $state<ThemePreference>(readStoredThemePreference());
  systemTheme = $state<ResolvedTheme>(readSystemTheme());

  get themePreference(): ThemePreference {
    return this._themePreference;
  }

  set themePreference(themePreference: ThemePreference) {
    this.setThemePreference(themePreference);
  }

  get theme(): ResolvedTheme {
    return this._themePreference === 'system' ? this.systemTheme : this._themePreference;
  }

  setThemePreference(themePreference: ThemePreference) {
    this._themePreference = themePreference;
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, themePreference);
      } catch {
        // Theme selection still works for the current session when storage is unavailable.
      }
    }
  }

  setTheme(theme: ResolvedTheme) {
    this.setThemePreference(theme);
  }

  toggleTheme() {
    this.setTheme(this.theme === 'dark' ? 'light' : 'dark');
  }

  startThemeSync() {
    if (typeof window === 'undefined') {
      return () => {};
    }

    this.systemTheme = readSystemTheme();
    const media = typeof window.matchMedia === 'function' ? window.matchMedia(THEME_QUERY) : undefined;
    const handleMediaChange = () => {
      this.systemTheme = media?.matches ? 'dark' : 'light';
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key === THEME_STORAGE_KEY) {
        this._themePreference = normalizeThemePreference(event.newValue);
      }
    };

    media?.addEventListener('change', handleMediaChange);
    window.addEventListener('storage', handleStorage);

    return () => {
      media?.removeEventListener('change', handleMediaChange);
      window.removeEventListener('storage', handleStorage);
    };
  }

  // Reads every persisted field so a caller can run this inside $effect and re-save on change.
  persistSettings() {
    const snapshot: PersistedSettings = {
      followActive: this.followActive,
      autoConfirmPrompts: this.autoConfirmPrompts,
      showLogs: this.showLogs,
      animateActions: this.animateActions,
      showActionSpotlight: this.showActionSpotlight,
      revealHands: this.revealHands,
      sortHand: this.sortHand,
      showMiniLog: this.showMiniLog,
      skin: this.skin,
      actionStepDelayMs: this.actionStepDelayMs,
    };
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // Settings still apply for the current session when storage is unavailable.
    }
  }

  resetPerspective() {
    this.boardTilt = DEFAULT_BOARD_TILT;
    this.boardPerspective = DEFAULT_BOARD_PERSPECTIVE;
    this.boardScaleY = DEFAULT_BOARD_SCALE_Y;
    this.boardLift = DEFAULT_BOARD_LIFT;
  }

  followPlayer(playerIndex: number) {
    this.viewIndex = playerIndex;
  }

  switchToPlayer(playerIndex: number) {
    this.followActive = false;
    this.viewIndex = playerIndex;
  }

  resetView() {
    this.followActive = true;
    this.viewIndex = 0;
  }
}

export const viewSettingsStore = new ViewSettingsStore();
