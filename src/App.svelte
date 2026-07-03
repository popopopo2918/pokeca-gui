<script lang="ts">
  import { onMount } from 'svelte';
  import ActiveFocus from './lib/components/ActiveFocus.svelte';
  import AppHeader from './lib/components/AppHeader.svelte';
  import DeckBuilderScreen from './lib/components/deckbuilder/DeckBuilderScreen.svelte';
  import { deckBuilderStore } from './state/deckBuilder.svelte';
  import { deckCountsToText } from './lib/cards/cardCatalog';
  import { SAMPLE_DECK } from './lib/game/deckImport';
  import CardZoom from './lib/components/CardZoom.svelte';
  import AgentManagerModal from './lib/components/AgentManagerModal.svelte';
  import BoardLayer from './lib/components/BoardLayer.svelte';
  import BoardPromptStrip from './lib/components/prompts/BoardPromptStrip.svelte';
  import EndGamePrompt from './lib/components/EndGamePrompt.svelte';
  import GameBoard from './lib/components/GameBoard.svelte';
  import GameStatus from './lib/components/GameStatus.svelte';
  import Hand from './lib/components/Hand.svelte';
  import ImportScreen from './lib/components/ImportScreen.svelte';
  import ActionSpotlight from './lib/components/ActionSpotlight.svelte';
  import TurnBanner from './lib/components/TurnBanner.svelte';
  import DrawFlyIn from './lib/components/DrawFlyIn.svelte';
  import LogPanel from './lib/components/LogPanel.svelte';
  import LogTicker from './lib/components/LogTicker.svelte';
  import PlayerPanel from './lib/components/PlayerPanel.svelte';
  import PromptGallery from './lib/components/prompt-gallery/PromptGallery.svelte';
  import PromptDock from './lib/components/prompts/PromptDock.svelte';
  import PromptHost from './lib/components/prompts/PromptHost.svelte';
  import ReplayTimeline from './lib/components/ReplayTimeline.svelte';
  import SetupDock from './lib/components/SetupDock.svelte';
  import TableShell from './lib/components/TableShell.svelte';
  import Toolbar from './lib/components/Toolbar.svelte';
  import ZoneViewer from './lib/components/ZoneViewer.svelte';
  import type { GameCommandApi } from './lib/game/gameApi';
  import { createRoomGameApi, localGameApi, roomApi, type PlayerControl } from './lib/game/httpClient';
  import { formatCabtDeckList } from './lib/game/deckImport';
  import { labelFor } from './lib/game/labels';
  import cardRows from './lib/cabt/cardData.generated.json';
  import type { BoardInteractionStrategy } from './lib/game/boardInteraction';
  import {
    canPlayCardToBoardArea,
    canPlayCardToPlayArea,
    canPlayCardToSlot,
    canPlayerAct,
    canRetreatToSlot,
    playableBenchSlot,
    type BoardPlayAreaContext,
  } from './lib/game/playTargets';
  import { benchSlotsFor, previewAttachEnergySlot, previewSlot } from './lib/game/preview';
  import {
    autoResolvablePromptResult,
    extractPromptCards,
    firstLegalCabtSelection,
    legalizeCabtSelection,
    promptBlockedIndexes,
    promptHasInteractiveUi,
    promptInstanceKey,
    promptOptions,
    shouldAutoResolvePrompt,
  } from './lib/game/prompts';
  import { getSetupPromptUiState, promptLimit, setupPromptResult } from './lib/game/setupPrompt';
  import { getAttachPromptTargets, getBoardPromptTargets, sameTarget, targetForPromptSlot } from './lib/game/targets';
  import { createChoosePokemonStrategy } from './lib/game/strategies/choosePokemonStrategy';
  import { createDamageTransferStrategy } from './lib/game/strategies/damageTransferStrategy';
  import { createPutDamageStrategy } from './lib/game/strategies/putDamageStrategy';
  import {
    loadAgentOptions,
    loadGameLogs,
    loadProfiles,
    createProfile,
    loadAllWorkspaceAgents,
    importSampleAgents,
    uploadWorkspaceAgent,
    deleteWorkspaceAgent,
    type AgentOption,
    type GameLogEntry,
  } from './lib/home/catalog';
  import {
    SlotType,
    targetFor,
    type CardTarget,
    type CardView,
    type GameView,
    type PlayerView,
    type PokemonSlotView,
    type PromptView,
  } from './lib/game/types';
  import { deckImportStore } from './state/deckImport.svelte';
  import { gameStore } from './state/game.svelte';
  import { boardGlowStore } from './state/boardGlow.svelte';
  import { gameSessionStore } from './state/gameSession.svelte';
  import { promptLifecycleStore } from './state/promptLifecycle.svelte';
  import { damageTransferStore } from './state/damageTransfer.svelte';
  import { promptSelectionStore } from './state/promptSelection.svelte';
  import { replayStore } from './state/replay.svelte';
  import {
    canAssignAttachTarget,
    isAttachEnergyAvailable as isAttachEnergyAvailableModel,
  } from './state/promptSelectionModel';
  import { selectionStore } from './state/selection.svelte';
  import { setupSelectionStore } from './state/setupSelection.svelte';
  import {
    canPlaceSetupActive as canPlaceSetupActiveModel,
    canPlaceSetupBench as canPlaceSetupBenchModel,
    isSetupStartable as isSetupStartableModel,
    type SetupPlacementContext,
  } from './state/setupSelectionModel';
  import { viewSettingsStore } from './state/viewSettings.svelte';
  import { zoneViewerStore } from './state/zoneViewer.svelte';

  type HomeMode = 'play' | 'logs';

  let showPromptGallery = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'prompt-gallery';
  const initialReplayMode = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'replay';
  const initialDeckBuilder = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'cards';
  let homeMode = $state<HomeMode>(initialReplayMode ? 'logs' : 'play');
  let deckBuilderOpen = $state(initialDeckBuilder);

  function applyBuiltDeck(playerIndex: 0 | 1, deckText: string) {
    if (playerIndex === 0) {
      deckImportStore.deck1Text = deckText;
      player1DeckSource = 'import';
      lastLoadedPlayer1DeckSource = '';
    } else {
      deckImportStore.deck2Text = deckText;
      player2DeckSource = 'import';
      lastLoadedPlayer2DeckSource = '';
    }
    homeMode = 'play';
    deckBuilderOpen = false;
  }

  // Keyboard shortcuts during a live match:
  // z = step back one move, x = step forward, l = toggle log panel, h = reveal concealed hands.
  function handleGlobalKeydown(event: KeyboardEvent) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    if (deckBuilderOpen || showPromptGallery || replayMode || !gameStore.game) {
      return;
    }
    const target = event.target as HTMLElement | null;
    const tag = target?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) {
      return;
    }
    const key = event.key.toLowerCase();
    if (key === 'z') {
      gameStore.stepBack();
      event.preventDefault();
    } else if (key === 'x') {
      gameStore.stepForward();
      event.preventDefault();
    } else if (key === 'l') {
      viewSettingsStore.showLogs = !viewSettingsStore.showLogs;
      event.preventDefault();
    } else if (key === 'h') {
      viewSettingsStore.revealHands = !viewSettingsStore.revealHands;
      event.preventDefault();
    }
  }
  let agents = $state<AgentOption[]>([]);
  let gameLogs = $state<GameLogEntry[]>([]);
  let profiles = $state<string[]>(['default']);
  let activeProfile = $state(
    typeof localStorage !== 'undefined' ? localStorage.getItem('cabt:activeProfile') || 'default' : 'default',
  );

  // Restore the last match setup (who is self/agent, which agents/decks) so repeat AI test
  // sessions start with one click. Agent/deck ids are re-validated in refreshCatalog().
  const MATCH_SETUP_STORAGE_KEY = 'cabt.matchSetup';
  type StoredMatchSetup = {
    player1Control?: PlayerControl;
    player2Control?: PlayerControl;
    player1AgentId?: string;
    player2AgentId?: string;
    player1DeckSource?: string;
    player2DeckSource?: string;
  };
  function readStoredMatchSetup(): StoredMatchSetup {
    if (typeof window === 'undefined') {
      return {};
    }
    try {
      const raw = window.localStorage.getItem(MATCH_SETUP_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return typeof parsed === 'object' && parsed !== null ? (parsed as StoredMatchSetup) : {};
    } catch {
      return {};
    }
  }
  function storedControl(value: PlayerControl | undefined, fallback: PlayerControl): PlayerControl {
    return value === 'self' || value === 'agent' ? value : fallback;
  }
  const storedMatchSetup = readStoredMatchSetup();

  let player1Control = $state<PlayerControl>(storedControl(storedMatchSetup.player1Control, 'self'));
  let player2Control = $state<PlayerControl>(storedControl(storedMatchSetup.player2Control, 'agent'));
  let player1AgentId = $state(typeof storedMatchSetup.player1AgentId === 'string' ? storedMatchSetup.player1AgentId : '');
  let player2AgentId = $state(typeof storedMatchSetup.player2AgentId === 'string' ? storedMatchSetup.player2AgentId : '');
  // 起動時の既定はフーディン（サンプルデッキ）。旧既定の「デッキを貼り付け」も
  // サンプルに置き換える（貼り付け内容は pasted バックアップに保持され、
  // 「デッキを貼り付け」を選び直せば戻る）。
  function storedDeckSource(value: string | undefined): string {
    return typeof value === 'string' && value && value !== 'import' ? value : 'preset:sample';
  }
  let player1DeckSource = $state(storedDeckSource(storedMatchSetup.player1DeckSource));
  let player2DeckSource = $state(storedDeckSource(storedMatchSetup.player2DeckSource));
  let activePlayerControls = $state<[PlayerControl, PlayerControl]>(['self', 'agent']);
  let lastLoadedPlayer1DeckSource = $state('');
  let lastLoadedPlayer2DeckSource = $state('');
  let player1DeckLoading = $state(false);
  let player2DeckLoading = $state(false);
  let catalogBusy = $state(false);
  let catalogError = $state('');
  let savingReplay = $state(false);
  let exportingLog = $state(false);
  let saveReplayMessage = $state('');
  let saveReplayError = $state('');
  let replayMode = $derived(homeMode === 'logs' && !!replayStore.replay);
  let game = $derived(replayMode ? replayStore.currentView : gameStore.displayView);
  let error = $derived(homeMode === 'logs' ? replayStore.error : gameStore.error);
  let busy = $derived(replayMode ? replayStore.loading : gameStore.busy);
  let sessionBusy = $derived(replayMode ? replayStore.loading : busy);
  // ---- オンライン対戦(遠隔ルーム) ----
  const ONLINE_ROOM_STORAGE_KEY = 'cabt.onlineRoom';
  let onlineRoom = $state<{ code: string; seat: number } | null>(readStoredOnlineRoom());
  let onlineWaiting = $state(false);
  let onlineBusy = $state(false);
  let lastRoomRevision = 0;
  let onlinePollInFlight = false;

  function readStoredOnlineRoom(): { code: string; seat: number } | null {
    try {
      const raw = localStorage.getItem(ONLINE_ROOM_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      return parsed && typeof parsed.code === 'string' && typeof parsed.seat === 'number' ? parsed : null;
    } catch {
      return null;
    }
  }

  let commandApi = $derived<GameCommandApi>(
    onlineRoom
      ? createRoomGameApi(onlineRoom.code, (revision) => {
          lastRoomRevision = Math.max(lastRoomRevision, revision);
        })
      : localGameApi,
  );
  let resolvingPrompt = $derived(gameStore.resolvingPrompt);
  let playingSequence = $derived(gameStore.playingSequence);
  let selectedHand = $derived(selectionStore.selectedHand);
  let draggingHand = $derived(selectionStore.draggingHand);
  let focusedSlot = $derived(selectionStore.focusedSlot);
  let setupActiveIndex = $derived(setupSelectionStore.activeIndex);
  let setupBenchIndexes = $derived(setupSelectionStore.benchIndexes);
  let attachPromptEnergyIndex = $derived(promptSelectionStore.activeAttachEnergyIndex);
  let attachPromptAssignments = $derived(promptSelectionStore.attachAssignments);
  let followActive = $derived(viewSettingsStore.followActive);
  let autoConfirmPrompts = $derived(viewSettingsStore.autoConfirmPrompts);
  let viewIndex = $derived(viewSettingsStore.viewIndex);
  let boardTilt = $derived(viewSettingsStore.boardTilt);
  let boardPerspective = $derived(viewSettingsStore.boardPerspective);
  let boardScaleY = $derived(viewSettingsStore.boardScaleY);
  let boardLift = $derived(viewSettingsStore.boardLift);
  let debugZones = $derived(viewSettingsStore.debugZones);
  let showLogs = $derived(viewSettingsStore.showLogs);
  let revealHands = $derived(viewSettingsStore.revealHands);
  let theme = $derived(viewSettingsStore.theme);
  let themePreference = $derived(viewSettingsStore.themePreference);
  let selectedPlayer1Agent = $derived(agents.find((agent) => agent.id === player1AgentId));
  let selectedPlayer2Agent = $derived(agents.find((agent) => agent.id === player2AgentId));
  let selectedPlayer1Deck = $derived(agents.find((agent) => agent.id === player1DeckSource && agent.deckUrl));
  let selectedPlayer2Deck = $derived(agents.find((agent) => agent.id === player2DeckSource && agent.deckUrl));
  onMount(() => {
    const stopThemeSync = viewSettingsStore.startThemeSync();
    deckBuilderStore.init();
    void initWorkspace();
    if (initialReplayMode) {
      void replayStore.loadSaved();
    }
    return stopThemeSync;
  });

  async function initWorkspace() {
    await loadProfileList();
    await refreshCatalog();
  }

  async function loadProfileList() {
    profiles = await loadProfiles();
    if (!profiles.includes(activeProfile)) {
      activeProfile = profiles[0] ?? 'default';
      persistActiveProfile();
    }
  }

  function persistActiveProfile() {
    try {
      localStorage.setItem('cabt:activeProfile', activeProfile);
    } catch {
      // localStorage unavailable; keep in-memory only.
    }
  }

  async function selectProfile(name: string) {
    if (name === activeProfile) return;
    activeProfile = name;
    persistActiveProfile();
    await refreshCatalog();
  }

  async function createNewProfile(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    profiles = await createProfile(trimmed);
    activeProfile = profiles.find((profile) => profile.toLowerCase() === trimmed.toLowerCase()) ?? trimmed;
    persistActiveProfile();
    await refreshCatalog();
  }

  async function importSamplesToProfile() {
    catalogBusy = true;
    catalogError = '';
    try {
      await importSampleAgents(activeProfile);
      await refreshCatalog();
    } catch (error) {
      catalogError = error instanceof Error ? error.message : String(error);
    } finally {
      catalogBusy = false;
    }
  }

  let agentManagerOpen = $state(false);
  let profileWorkspaceAgents = $derived(agents.filter((agent) => agent.id.startsWith(`ws:${activeProfile}:`)));

  async function uploadAgentToProfile(name: string, mainPy: string, deckCsv: string) {
    const result = await uploadWorkspaceAgent(activeProfile, name, mainPy, deckCsv);
    if (result.ok) {
      await refreshCatalog();
    }
    return result;
  }

  async function deleteAgentFromProfile(name: string) {
    await deleteWorkspaceAgent(activeProfile, name);
    await refreshCatalog();
  }
  $effect(() => {
    viewSettingsStore.persistSettings();
  });
  $effect(() => {
    deckImportStore.persist();
  });
  $effect(() => {
    const snapshot: StoredMatchSetup = {
      player1Control,
      player2Control,
      player1AgentId,
      player2AgentId,
      player1DeckSource,
      player2DeckSource,
    };
    try {
      localStorage.setItem(MATCH_SETUP_STORAGE_KEY, JSON.stringify(snapshot));
    } catch {
      // Match setup still applies for the current session when storage is unavailable.
    }
  });
  $effect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.themePreference = themePreference;
    document.documentElement.style.colorScheme = theme;
  });
  $effect(() => {
    document.body.classList.toggle('prompt-gallery-page', showPromptGallery);
    return () => {
      document.body.classList.remove('prompt-gallery-page');
    };
  });
  // AIのペアデッキは「そのAIを選んだ時の初期値」としてだけ適用し、以後は
  // 自由に別のデッキ（サンプル・保存デッキ・貼り付け）へ変更できる。
  let lastPairedAgent1 = typeof storedMatchSetup.player1AgentId === 'string' ? storedMatchSetup.player1AgentId : '';
  let lastPairedAgent2 = typeof storedMatchSetup.player2AgentId === 'string' ? storedMatchSetup.player2AgentId : '';
  $effect(() => {
    if (player1Control === 'agent' && selectedPlayer1Agent?.deckUrl && lastPairedAgent1 !== selectedPlayer1Agent.id) {
      lastPairedAgent1 = selectedPlayer1Agent.id;
      player1DeckSource = selectedPlayer1Agent.id;
    }
  });
  $effect(() => {
    if (player2Control === 'agent' && selectedPlayer2Agent?.deckUrl && lastPairedAgent2 !== selectedPlayer2Agent.id) {
      lastPairedAgent2 = selectedPlayer2Agent.id;
      player2DeckSource = selectedPlayer2Agent.id;
    }
  });
  // 「デッキを貼り付け」の内容は、他のデッキへ切り替える時に退避し、戻ったら復元する。
  let prevDeckSource1 = player1DeckSource;
  let prevDeckSource2 = player2DeckSource;
  $effect(() => {
    const source = player1DeckSource;
    if (source === prevDeckSource1) return;
    if (prevDeckSource1 === 'import') deckImportStore.pasted1 = deckImportStore.deck1Text;
    if (source === 'import') deckImportStore.deck1Text = deckImportStore.pasted1;
    prevDeckSource1 = source;
  });
  $effect(() => {
    const source = player2DeckSource;
    if (source === prevDeckSource2) return;
    if (prevDeckSource2 === 'import') deckImportStore.pasted2 = deckImportStore.deck2Text;
    if (source === 'import') deckImportStore.deck2Text = deckImportStore.pasted2;
    prevDeckSource2 = source;
  });
  $effect(() => {
    if (player1DeckSource.startsWith('deck:') || player1DeckSource.startsWith('preset:')) {
      return; // saved-deck/preset sources are filled by the saved-deck effect below
    }
    const deckUrl = selectedPlayer1Deck?.deckUrl ?? '';
    if (player1DeckSource === 'import' || !deckUrl) {
      lastLoadedPlayer1DeckSource = '';
      return;
    }
    if (player1DeckSource === lastLoadedPlayer1DeckSource) {
      return;
    }
    void loadSelectedDeck(deckUrl, player1DeckSource, 0);
  });
  $effect(() => {
    if (player2DeckSource.startsWith('deck:') || player2DeckSource.startsWith('preset:')) {
      return;
    }
    const deckUrl = selectedPlayer2Deck?.deckUrl ?? '';
    if (player2DeckSource === 'import' || !deckUrl) {
      lastLoadedPlayer2DeckSource = '';
      return;
    }
    if (player2DeckSource === lastLoadedPlayer2DeckSource) {
      return;
    }
    void loadSelectedDeck(deckUrl, player2DeckSource, 1);
  });
  // 「デッキ編成」で保存したデッキを対戦画面の選択肢から直接使えるようにする。
  $effect(() => {
    applySavedDeckSource(player1DeckSource, 0);
  });
  $effect(() => {
    applySavedDeckSource(player2DeckSource, 1);
  });

  function applySavedDeckSource(source: string, playerIndex: 0 | 1) {
    if (!source.startsWith('deck:') && source !== 'preset:sample') {
      return;
    }
    const lastLoaded = playerIndex === 0 ? lastLoadedPlayer1DeckSource : lastLoadedPlayer2DeckSource;
    if (lastLoaded === source) {
      return;
    }
    let text: string;
    if (source === 'preset:sample') {
      text = SAMPLE_DECK;
    } else {
      const deck = deckBuilderStore.library.find((item) => `deck:${item.id}` === source);
      if (!deck) {
        if (playerIndex === 0) player1DeckSource = 'import';
        else player2DeckSource = 'import';
        return;
      }
      text = deckCountsToText(deck.counts);
    }
    if (playerIndex === 0) {
      deckImportStore.deck1Text = text;
      lastLoadedPlayer1DeckSource = source;
    } else {
      deckImportStore.deck2Text = text;
      lastLoadedPlayer2DeckSource = source;
    }
  }
  let zoneViewerOpen = $derived(zoneViewerStore.open);
  let zoneViewerTitle = $derived(zoneViewerStore.title);
  let zoneViewerFaceDown = $derived(zoneViewerStore.faceDown);
  let zoneViewerIsStadium = $derived(zoneViewerStore.zone === 'stadium');
  let activePlayer = $derived(game?.players[game.activePlayerIndex]);
  let bottomPlayer = $derived(game?.players[viewIndex] ?? game?.players[0]);
  let topPlayer = $derived(game?.players.find((player) => player.index !== bottomPlayer?.index));
  // オンライン対戦では相手のプロンプト（内容はサーバー側でマスク済み）を自分のUIに
  // 出さない。相手の手番であることは待機インジケーターで示す。
  let currentPrompt = $derived.by(() => {
    if (replayMode) return null;
    const prompt = game?.prompts[0];
    if (prompt && onlineRoom && prompt.fields?.playbackOnly !== true && prompt.playerIndex !== onlineRoom.seat) {
      return null;
    }
    return prompt;
  });
  let onlineOpponentActing = $derived(
    !!onlineRoom && !!game && game.ready !== false && game.phase !== 7
      && (game.prompts[0]?.playerIndex ?? game.activePlayerIndex) !== onlineRoom.seat,
  );
  let actingPlayerIndex = $derived(currentPrompt?.playerIndex ?? game?.activePlayerIndex ?? 0);
  let actingPlayerIsSelf = $derived(activePlayerControls[actingPlayerIndex] === 'self');
  // Hotseat (self vs self) hides the non-acting hand for privacy; vs AI the human's
  // own hand must stay visible even while the opponent is taking their turn.
  let bothPlayersSelf = $derived(activePlayerControls[0] === 'self' && activePlayerControls[1] === 'self');
  let modeLabel = $derived(`${controlLabel(activePlayerControls[0])} vs ${controlLabel(activePlayerControls[1])}`);
  let boardTargetPrompt = $derived(currentPrompt?.className === 'ChoosePokemonPrompt' ? currentPrompt : null);
  let attachPrompt = $derived(currentPrompt?.className === 'AttachEnergyPrompt' ? currentPrompt : null);
  let damagePrompt = $derived(currentPrompt?.className === 'PutDamagePrompt' ? currentPrompt : null);
  let attachPromptCards = $derived(attachPrompt ? extractPromptCards(attachPrompt.fields) : []);
  let attachPromptMin = $derived(normalizePromptLimit(promptOptions(attachPrompt).min, 0));
  let attachPromptMax = $derived(normalizePromptLimit(promptOptions(attachPrompt).max, attachPromptCards.length || 1));
  let attachPromptTargets = $derived(attachPrompt && game ? getAttachPromptTargets(game, attachPrompt) : []);
  let damagePromptTargets = $derived(damagePrompt && game ? getBoardPromptTargets(game, damagePrompt) : []);
  let damagePromptInstanceKey = $derived(promptInstanceKey(damagePrompt));
  let lastDamagePromptInstanceKey = $state('');
  $effect(() => {
    promptSelectionStore.pruneAttachAssignments(attachPromptCards, attachPromptTargets, attachPromptMax);
  });
  $effect(() => {
    promptSelectionStore.clearUnavailableAttachEnergy(isAttachEnergyAvailable);
  });
  $effect(() => {
    promptSelectionStore.pruneDamagePlacements(damagePromptTargets);
  });
  $effect(() => {
    if (damagePromptInstanceKey !== lastDamagePromptInstanceKey) {
      promptSelectionStore.resetDamagePlacements();
      lastDamagePromptInstanceKey = damagePromptInstanceKey;
    }
  });

  let transferPrompt = $derived(
    currentPrompt?.className === 'MoveDamagePrompt' || currentPrompt?.className === 'RemoveDamagePrompt'
      ? currentPrompt
      : null,
  );
  let transferPromptInstanceKey = $derived(promptInstanceKey(transferPrompt));
  let lastTransferPromptInstanceKey = $state('');
  $effect(() => {
    if (transferPromptInstanceKey !== lastTransferPromptInstanceKey) {
      damageTransferStore.reset();
      lastTransferPromptInstanceKey = transferPromptInstanceKey;
    }
  });
  let boardTargetPromptInstanceKey = $derived(promptInstanceKey(boardTargetPrompt));
  let lastBoardTargetPromptInstanceKey = $state('');
  $effect(() => {
    if (boardTargetPromptInstanceKey !== lastBoardTargetPromptInstanceKey) {
      promptSelectionStore.resetBoardTargets();
      lastBoardTargetPromptInstanceKey = boardTargetPromptInstanceKey;
    }
  });
  let boardStrategy = $derived<BoardInteractionStrategy | null>(
    game && currentPrompt ? createBoardStrategy(game, currentPrompt) : null,
  );
  $effect(() => {
    if (!boardStrategy || !game) {
      return;
    }
    window.addEventListener('click', clickBoardPromptSlotAtPoint, true);
    return () => {
      window.removeEventListener('click', clickBoardPromptSlotAtPoint, true);
    };
  });
  let autoResolvePromptResult = $derived(autoResolvablePromptResult(currentPrompt, game));
  let autoResolvePrompt = $derived(
    shouldAutoResolvePrompt(currentPrompt, autoConfirmPrompts, autoResolvePromptResult, !actingPlayerIsSelf),
  );
  let setupPrompt = $derived(
    currentPrompt?.className === 'ChooseCardsPrompt' && currentPrompt.message === 'CHOOSE_STARTING_POKEMONS'
      ? currentPrompt
      : null,
  );
  let setupPlayer = $derived(setupPrompt && game ? game.players[setupPrompt.playerIndex] : undefined);
  let setupBlockedIndexes = $derived(new Set<number>(promptBlockedIndexes(setupPrompt)));
  let setupUi = $derived(getSetupPromptUiState(promptOptions(setupPrompt), setupPlayer, setupActiveIndex));
  let setupMinSelections = $derived(setupUi.minSelections);
  let setupMaxSelections = $derived(setupUi.maxSelections);
  let setupHasEngineActive = $derived(setupUi.hasEngineActive);
  let setupNeedsActive = $derived(!!setupPrompt && setupUi.needsActive);
  let setupCanConfirm = $derived(!!setupPrompt && setupUi.canConfirm);
  let setupPlayableIndexes = $derived(setupPlayer
    ? setupPlayer.hand
        .map((card, index) => ({ card, index }))
        .filter(({ card, index }) => isSetupStartable(card, index))
        .map(({ index }) => index)
    : []);
  let setupPlacedIndexes = $derived(setupSelectionStore.placedIndexes);
  let setupSelectedIndex = $derived(
    selectedHand && setupPrompt?.playerIndex === selectedHand.playerIndex && setupPlayableIndexes.includes(selectedHand.handIndex)
      ? selectedHand.handIndex
      : undefined,
  );
  let setupPlacementContext = $derived<SetupPlacementContext>({
    promptPlayerIndex: setupPrompt?.playerIndex,
    selectedHandIndex: setupSelectedIndex,
    hasEngineActive: setupHasEngineActive,
    activeIndex: setupActiveIndex,
    benchIndexes: setupBenchIndexes,
    minSelections: setupMinSelections,
    benchCapacity: setupUi.benchCapacity,
  });

  function resetPerspective() {
    viewSettingsStore.resetPerspective();
  }

  function createBoardStrategy(currentGame: GameView, prompt: PromptView) {
    if (prompt.className === 'PutDamagePrompt') {
      return createPutDamageStrategy({
        game: currentGame,
        prompt,
        store: promptSelectionStore,
        resolve: (value) => void resolvePrompt(value),
      });
    }
    if (prompt.className === 'MoveDamagePrompt' || prompt.className === 'RemoveDamagePrompt') {
      return createDamageTransferStrategy({
        game: currentGame,
        prompt,
        store: damageTransferStore,
        resolve: (value) => void resolvePrompt(value),
      });
    }
    if (prompt.className === 'ChoosePokemonPrompt') {
      return createChoosePokemonStrategy({
        game: currentGame,
        prompt,
        store: promptSelectionStore,
        resolve: (value) => void resolvePrompt(value),
      });
    }
    return null;
  }

  $effect(() => {
    // オンライン対戦では常に自分の席を手前に固定する（相手手番でも視点を回さない）。
    if (game && (followActive || actingPlayerIsSelf) && !replayMode && !playingSequence && !onlineRoom) {
      viewSettingsStore.followPlayer(actingPlayerIndex);
    }
  });
  let gameFinished = $derived(game?.phase === 7);
  let winnerName = $derived(
    game?.winner === 0 || game?.winner === 1
      ? game.players[game.winner]?.name
      : undefined,
  );
  let gameResultLabel = $derived(
    game?.winner === 3
      ? '引き分け'
      : winnerName
        ? `${winnerName} の勝ち`
        : gameFinished
          ? '対戦終了'
          : '',
  );
  let currentPromptDockMode = $derived<'default' | 'search' | 'attachEnergy'>(
    currentPrompt?.className === 'ChooseCardsPrompt'
      ? 'search'
      : currentPrompt?.className === 'AttachEnergyPrompt'
        ? 'attachEnergy'
        : 'default',
  );
  let retreatSource = $state<PokemonSlotView | null>(null);
  let selectedCard = $derived(selectedHand && game ? game.players[selectedHand.playerIndex]?.hand[selectedHand.handIndex] : undefined);
  let draggingCard = $derived(draggingHand && game ? game.players[draggingHand.playerIndex]?.hand[draggingHand.handIndex] : undefined);
  let currentStadium = $derived(game ? game.players.flatMap((player) => player.stadium)[0] : undefined);
  let currentStadiumOwner = $derived(game?.players.find((player) => player.stadium.length));
  let viewedCards = $derived(zoneViewerStore.cardsFor(game));
  let focusedPlayer = $derived(focusedSlot && game ? game.players[focusedSlot.ownerIndex] : undefined);
  let focusedIsActive = $derived(focusedSlot?.slot === 'active');
  let focusedCanAct = $derived(!!focusedPlayer && canAct(focusedPlayer.index));
  let focusedBenchTargets = $derived(focusedPlayer?.bench.filter((slot) => !slot.empty) ?? []);
  let topActiveSlot = $derived(topPlayer
    ? previewAttachEnergySlot(
        previewSlot(
          topPlayer.active,
          topPlayer.index === setupPrompt?.playerIndex && setupActiveIndex !== null ? topPlayer.hand[setupActiveIndex] : undefined,
        ),
        attachPrompt,
        attachPromptAssignments,
        attachPromptCards,
      )
    : undefined);
  let bottomActiveSlot = $derived(bottomPlayer
    ? previewAttachEnergySlot(
        previewSlot(
          bottomPlayer.active,
          bottomPlayer.index === setupPrompt?.playerIndex && setupActiveIndex !== null ? bottomPlayer.hand[setupActiveIndex] : undefined,
        ),
        attachPrompt,
        attachPromptAssignments,
        attachPromptCards,
      )
    : undefined);
  let topBenchSlots = $derived(topPlayer
    ? benchSlotsFor(topPlayer, setupPrompt, setupBenchIndexes).map((slot) =>
        previewAttachEnergySlot(slot, attachPrompt, attachPromptAssignments, attachPromptCards),
      )
    : []);
  let bottomBenchSlots = $derived(bottomPlayer
    ? benchSlotsFor(bottomPlayer, setupPrompt, setupBenchIndexes).map((slot) =>
        previewAttachEnergySlot(slot, attachPrompt, attachPromptAssignments, attachPromptCards),
      )
    : []);
  let canPlayOnBoard = $derived(
    !!bottomPlayer &&
    canPlayCardToBoardArea({
      selected: selectedCard,
      selectedPlayerIndex: selectedHand?.playerIndex,
      dragging: draggingCard,
      draggingPlayerIndex: draggingHand?.playerIndex,
      activePlayerIndex: game?.activePlayerIndex,
      hasPrompt: !!currentPrompt,
      finished: gameFinished,
      inSetup: !!setupPrompt,
    } satisfies BoardPlayAreaContext),
  );
  $effect(() => {
    if (currentPrompt || gameFinished) {
      selectionStore.clearFocus();
    }
  });
  $effect(() => {
    if (promptLifecycleStore.shouldAutoConfirm(currentPrompt, autoResolvePrompt, resolvingPrompt)) {
      void resolvePrompt(autoResolvePromptResult);
    }
  });

  // Glow the Pokémon on the board when its Ability is used, so it is obvious which card acted.
  // The engine bridge injects a synthetic 'ability' log (with the source Pokémon) whenever an
  // ability option is chosen, so this is a reliable signal for both players.
  let abilityUseEvent = $derived.by(() => {
    const timeline = game?.actionTimeline;
    if (!timeline) return undefined;
    for (let index = timeline.length - 1; index >= 0; index -= 1) {
      const event = timeline[index];
      if (event.kind === 'ability' && event.playerIndex !== undefined) {
        return event;
      }
    }
    return undefined;
  });
  let lastAbilityGlowId = $state(-1);
  $effect(() => {
    const event = abilityUseEvent;
    if (event && event.id !== lastAbilityGlowId && event.playerIndex !== undefined) {
      lastAbilityGlowId = event.id;
      const cardId = Number((event.params as { cardId?: unknown }).cardId);
      boardGlowStore.glow(event.playerIndex, cardId, Math.max(viewSettingsStore.actionStepDelayMs, 1400));
    }
  });

  async function startGame() {
    if (!(await ensureSelectedDecksLoaded())) {
      return;
    }
    const decks = deckImportStore.parseLocalGameDecks();
    if (!decks.ok) {
      gameStore.setError(decks.error);
      return;
    }

    selectionStore.setSelectedHand(null);
    resetSaveReplayStatus();
    sessionResultRecorded = false;
    resetSessionTallyIfMatchupChanged();
    replayStore.clear();
    gameStore.reset();
    homeMode = 'play';
    activePlayerControls = [player1Control, player2Control];
    await gameSessionStore.run(() =>
      localGameApi.start(decks.player1Cards, decks.player2Cards, {
        player1Control,
        player2Control,
        player1AgentId,
        player2AgentId,
      }),
    );
  }

  // ---- オンライン対戦: ルームの作成・参加・同期 ----

  function enterOnlineRoom(code: string, seat: number, started: boolean) {
    gameSessionStore.reset();
    replayStore.clear();
    resetSaveReplayStatus();
    onlineRoom = { code, seat };
    lastRoomRevision = 0;
    onlineWaiting = !started;
    activePlayerControls = seat === 0 ? ['self', 'agent'] : ['agent', 'self'];
    viewSettingsStore.viewIndex = seat;
    homeMode = 'play';
    try {
      localStorage.setItem(ONLINE_ROOM_STORAGE_KEY, JSON.stringify(onlineRoom));
    } catch {
      // 再接続の補助が効かないだけで、対戦は続行できる
    }
  }

  function leaveOnlineRoom(notifyServer = true) {
    if (!onlineRoom) {
      return;
    }
    if (notifyServer) {
      void roomApi.leave(onlineRoom.code).catch(() => undefined);
    }
    onlineRoom = null;
    onlineWaiting = false;
    lastRoomRevision = 0;
    try {
      localStorage.removeItem(ONLINE_ROOM_STORAGE_KEY);
    } catch {
      // no-op
    }
  }

  async function createOnlineRoom() {
    if (onlineBusy) return;
    const parsed = deckImportStore.parseRemoteDeck();
    if (!parsed.ok) {
      gameStore.setError(parsed.error);
      return;
    }
    onlineBusy = true;
    try {
      const response = await roomApi.create(parsed.cards);
      if (!response.ok || !response.code) {
        gameStore.setError(response.error ?? 'ルームを作成できませんでした。');
        return;
      }
      enterOnlineRoom(response.code, response.seat ?? 0, false);
    } catch (error) {
      gameStore.setError(`ルーム作成に失敗しました: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      onlineBusy = false;
    }
  }

  async function joinOnlineRoom(code: string) {
    if (onlineBusy || !code.trim()) return;
    const parsed = deckImportStore.parseRemoteDeck();
    if (!parsed.ok) {
      gameStore.setError(parsed.error);
      return;
    }
    onlineBusy = true;
    try {
      const response = await roomApi.join(code, parsed.cards);
      if (!response.ok) {
        gameStore.setError(response.error ?? 'ルームに参加できませんでした。');
        return;
      }
      enterOnlineRoom(code.trim().toUpperCase(), response.seat ?? 1, response.started ?? true);
    } catch (error) {
      gameStore.setError(`ルーム参加に失敗しました: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      onlineBusy = false;
    }
  }

  // 対戦状態のポーリング同期（1.5秒間隔）。自分の操作中はスキップし、
  // revision の進んだ差分フレームだけを適用する。
  $effect(() => {
    if (!onlineRoom) {
      return;
    }
    const room = onlineRoom;
    const timer = setInterval(() => void pollOnlineRoom(room.code), 1500);
    void pollOnlineRoom(room.code);
    return () => clearInterval(timer);
  });

  async function pollOnlineRoom(code: string) {
    if (onlinePollInFlight || !onlineRoom || onlineRoom.code !== code) {
      return;
    }
    if (gameStore.busy || gameStore.resolvingPrompt || gameStore.playingSequence) {
      return;
    }
    onlinePollInFlight = true;
    try {
      const state = await roomApi.state(code, lastRoomRevision);
      if (!onlineRoom || onlineRoom.code !== code) {
        return;
      }
      if (!state.ok) {
        gameStore.setError(state.error ?? 'ルームとの接続が失われました。');
        leaveOnlineRoom(false);
        return;
      }
      onlineWaiting = !state.started;
      if (state.started && typeof state.revision === 'number' && state.revision > lastRoomRevision && state.view) {
        lastRoomRevision = state.revision;
        await gameSessionStore.applyExternal({ ok: true, view: state.view, sequence: state.sequence });
      }
    } catch {
      // 一時的な通信エラーは次のポーリングで回復する
    } finally {
      onlinePollInFlight = false;
    }
  }

  // Restart from the end-game screen without flashing the import screen while the
  // new match is being created.
  let rematching = $state(false);

  async function rematch(swapSides: boolean) {
    if (rematching) {
      return;
    }
    rematching = true;
    try {
      if (swapSides) {
        // Swap sides so the same AI can be tested going both first and second.
        const deck1 = deckImportStore.deck1Text;
        deckImportStore.deck1Text = deckImportStore.deck2Text;
        deckImportStore.deck2Text = deck1;
        [player1Control, player2Control] = [player2Control, player1Control];
        [player1AgentId, player2AgentId] = [player2AgentId, player1AgentId];
        [player1DeckSource, player2DeckSource] = [player2DeckSource, player1DeckSource];
        [lastLoadedPlayer1DeckSource, lastLoadedPlayer2DeckSource] = [lastLoadedPlayer2DeckSource, lastLoadedPlayer1DeckSource];
        // Swapping sides also swaps which player index the session tally belongs to.
        sessionWins = [sessionWins[1], sessionWins[0]];
      }
      await startGame();
    } finally {
      rematching = false;
    }
  }

  async function refreshCatalog() {
    catalogBusy = true;
    catalogError = '';
    try {
      const [officialAgents, nextLogs, profileAgents] = await Promise.all([
        loadAgentOptions(),
        loadGameLogs(),
        loadAllWorkspaceAgents(),
      ]);
      const nextAgents = [...officialAgents, ...profileAgents];
      agents = nextAgents;
      gameLogs = nextLogs;
      if (!player1AgentId || !nextAgents.some((agent) => agent.id === player1AgentId)) {
        player1AgentId = nextAgents[0]?.id ?? '';
      }
      if (!player2AgentId || !nextAgents.some((agent) => agent.id === player2AgentId)) {
        player2AgentId = nextAgents[0]?.id ?? '';
      }
      if (player1DeckSource !== 'import' && !player1DeckSource.startsWith('deck:') && !player1DeckSource.startsWith('preset:')
        && !nextAgents.some((agent) => agent.id === player1DeckSource && agent.deckUrl)) {
        player1DeckSource = 'import';
      }
      if (player2DeckSource !== 'import' && !player2DeckSource.startsWith('deck:') && !player2DeckSource.startsWith('preset:')
        && !nextAgents.some((agent) => agent.id === player2DeckSource && agent.deckUrl)) {
        player2DeckSource = 'import';
      }
    } catch (error) {
      catalogError = error instanceof Error ? error.message : String(error);
    } finally {
      catalogBusy = false;
    }
  }

  async function ensureSelectedDecksLoaded() {
    const player1Loaded = await ensureDeckLoaded(player1DeckSource, 0);
    const player2Loaded = await ensureDeckLoaded(player2DeckSource, 1);
    return player1Loaded && player2Loaded;
  }

  async function ensureDeckLoaded(deckSource: string, playerIndex: number) {
    if (deckSource === 'import') {
      return true;
    }
    const lastLoaded = playerIndex === 0 ? lastLoadedPlayer1DeckSource : lastLoadedPlayer2DeckSource;
    if (lastLoaded === deckSource) {
      return true;
    }
    const deckUrl = agents.find((agent) => agent.id === deckSource)?.deckUrl;
    if (!deckUrl) {
      return true;
    }
    return loadSelectedDeck(deckUrl, deckSource, playerIndex);
  }

  async function loadSelectedDeck(deckUrl: string, deckSource: string, playerIndex: number) {
    if (playerIndex === 0) {
      player1DeckLoading = true;
    } else {
      player2DeckLoading = true;
    }
    try {
      const response = await fetch(deckUrl);
      if (!response.ok) {
        throw new Error(`${deckUrl}: ${response.status}`);
      }
      const deckText = formatCabtDeckList(await response.text(), cardRows);
      if (playerIndex === 0) {
        deckImportStore.deck1Text = deckText;
        lastLoadedPlayer1DeckSource = deckSource;
      } else {
        deckImportStore.deck2Text = deckText;
        lastLoadedPlayer2DeckSource = deckSource;
      }
      return true;
    } catch (error) {
      catalogError = error instanceof Error ? error.message : String(error);
      return false;
    } finally {
      if (playerIndex === 0) {
        player1DeckLoading = false;
      } else {
        player2DeckLoading = false;
      }
    }
  }

  async function loadGameLog(log: GameLogEntry) {
    gameSessionStore.reset();
    resetSaveReplayStatus();
    zoneViewerStore.close();
    viewSettingsStore.resetView();
    activePlayerControls = ['self', 'self'];
    homeMode = 'logs';
    await replayStore.loadSaved(log.file || log.id);
  }

  async function saveReplay() {
    if (savingReplay) {
      return;
    }
    savingReplay = true;
    saveReplayMessage = '';
    saveReplayError = '';
    try {
      const response = await localGameApi.saveReplay();
      if (!response.ok) {
        throw new Error(response.error ?? '対戦を保存できませんでした。');
      }
      saveReplayMessage = response.file ? `対戦ログに保存しました（${response.file}）。` : '対戦ログに保存しました。';
      await refreshCatalog();
    } catch (error) {
      saveReplayError = error instanceof Error ? error.message : String(error);
    } finally {
      savingReplay = false;
    }
  }

  async function exportLog() {
    if (exportingLog || replayMode) {
      return;
    }
    exportingLog = true;
    saveReplayError = '';
    try {
      const response = await localGameApi.saveReplay();
      if (!response.ok || !response.file) {
        throw new Error(response.error ?? '対戦ログを書き出せませんでした。');
      }
      saveReplayMessage = `対戦ログに保存しました（${response.file}）。`;
      await refreshCatalog();
      const fileResponse = await fetch(`/game-logs/${response.file}`);
      const blob = await fileResponse.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = response.file;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      saveReplayError = error instanceof Error ? error.message : String(error);
    } finally {
      exportingLog = false;
    }
  }

  // Auto-save the match log once when a live game finishes (uses the live game, not the reviewed frame).
  // オンライン対戦の記録はルーム側のエンジンにあるため、ここでは保存しない。
  $effect(() => {
    if (!replayMode && !onlineRoom && gameStore.gameFinished && !savingReplay && !saveReplayMessage && !saveReplayError) {
      void saveReplay();
    }
  });

  // Session win/loss tally across rematches, so repeated AI test runs show a running score.
  let sessionWins = $state<[number, number]>([0, 0]);
  let sessionDraws = $state(0);
  let sessionResultRecorded = $state(false);
  let sessionMatchupKey = $state('');

  // The tally only makes sense for one matchup. Reset it when decks/controls/agents change;
  // the key is order-independent so a side-swapped rematch keeps (and swaps) the tally.
  function resetSessionTallyIfMatchupChanged() {
    const sideSignature = (control: PlayerControl, agentId: string, deckText: string) =>
      `${control}|${control === 'agent' ? agentId : ''}|${deckText.trim()}`;
    const key = [
      sideSignature(player1Control, player1AgentId, deckImportStore.deck1Text),
      sideSignature(player2Control, player2AgentId, deckImportStore.deck2Text),
    ]
      .sort()
      .join('~~');
    if (key !== sessionMatchupKey) {
      sessionMatchupKey = key;
      sessionWins = [0, 0];
      sessionDraws = 0;
    }
  }
  $effect(() => {
    if (replayMode || !gameStore.gameFinished || sessionResultRecorded) {
      return;
    }
    sessionResultRecorded = true;
    const winner = gameStore.game?.winner;
    if (winner === 0 || winner === 1) {
      sessionWins[winner] += 1;
    } else if (winner === 3) {
      sessionDraws += 1;
    }
  });
  let sessionRecordLabel = $derived.by(() => {
    const total = sessionWins[0] + sessionWins[1] + sessionDraws;
    if (!game || total === 0) {
      return '';
    }
    const players = game.players;
    const drawPart = sessionDraws > 0 ? ` ／ 引き分け ${sessionDraws}` : '';
    return `通算 ${total}戦: ${players[0]?.name ?? 'プレイヤー1'} ${sessionWins[0]}勝 ／ ${players[1]?.name ?? 'プレイヤー2'} ${sessionWins[1]}勝${drawPart}`;
  });

  async function playToTarget(target: CardTarget) {
    if (!selectedHand || !game || !canAct(selectedHand.playerIndex)) {
      return;
    }
    // One board action per gesture: a click on a slot also bubbles to the board/bench
    // area handlers, which used to send the same playCard twice — the duplicate then
    // answered the card effect's follow-up selection by itself.
    if (gameStore.busy || gameStore.resolvingPrompt) {
      return;
    }
    await gameSessionStore.run(() => commandApi.playCard(selectedHand!.playerIndex, selectedHand!.handIndex, target));
  }

  function playToSlot(slot: PokemonSlotView) {
    if (!isPlayableTarget(slot)) {
      return;
    }
    void playToTarget(slot.target);
  }

  function clickSlot(slot: PokemonSlotView) {
    if (attachPrompt && isBoardPromptSelectable(slot)) {
      assignAttachPromptTarget(slot);
      return;
    }

    if (dispatchBoardClick(slot)) {
      return;
    }

    if (canPlaceSetupActive(slot)) {
      placeSetupActive();
      return;
    }

    if (setupPrompt && slot.ownerIndex === setupPrompt.playerIndex && !selectedHand) {
      if (slot.slot === 'active' && setupActiveIndex !== null) {
        removeSetupIndex(setupActiveIndex);
        return;
      }
      if (slot.slot === 'bench' && setupBenchIndexes[slot.index] !== undefined) {
        removeSetupIndex(setupBenchIndexes[slot.index]);
        return;
      }
    }

    if (isPlayableTarget(slot)) {
      playToSlot(slot);
      return;
    }

    if (canPlayOnBoard) {
      playSelectedToBoard();
      return;
    }

    if (!slot.empty && slot.pokemon) {
      selectionStore.focusSlot(slot);
    }
  }

  async function attack(name: string) {
    if (!game || !focusedPlayer || !focusedIsActive || !focusedCanAct || gameStore.busy) return;
    await gameSessionStore.run(() => commandApi.attack(focusedPlayer!.index, name));
  }

  async function useAbility(name: string, target: CardTarget) {
    if (!game || !focusedPlayer || !focusedCanAct || gameStore.busy) return;
    await gameSessionStore.run(() => commandApi.useAbility(focusedPlayer!.index, name, target));
  }

  async function useStadium() {
    if (!game || !activePlayer || !canAct(activePlayer.index) || gameStore.busy) return;
    zoneViewerStore.close();
    await gameSessionStore.run(() => commandApi.useStadium(activePlayer.index));
  }

  async function concede() {
    if (!game || !activePlayer || gameFinished) return;
    // Guard against a stray click ending a long test match.
    if (!window.confirm(`${activePlayer.name} が投了して対戦を終了します。よろしいですか？`)) {
      return;
    }
    await gameSessionStore.run(() => commandApi.concede(game.activePlayerIndex));
  }

  async function passTurn() {
    if (!game || gameStore.busy) return;
    await gameSessionStore.run(() => commandApi.passTurn(game.activePlayerIndex));
  }

  // Rewind the engine to the previous main-phase decision so a different move can be
  // played. Hidden cards (deck order, prizes, unseen hands) are re-randomized.
  async function undoMove() {
    if (!game || replayMode || gameStore.undoCount <= 0) return;
    gameStore.returnToLive();
    selectionStore.clearAll();
    retreatSource = null;
    const response = await gameSessionStore.run(() => commandApi.undo(1));
    if (response.ok) {
      gameStore.restartHistoryFromCurrent();
    }
  }

  async function retreat(to: number) {
    if (!game || gameStore.busy) return;
    retreatSource = null;
    await gameSessionStore.run(() => commandApi.retreat(game.activePlayerIndex, to));
  }

  function canRetreatToSelectedTarget(slot: PokemonSlotView) {
    if (!game || !retreatSource || slot.slot !== 'bench' || slot.empty || slot.ownerIndex !== retreatSource.ownerIndex) {
      return false;
    }
    const retreatAction = game.players[retreatSource.ownerIndex]?.availableActions?.active?.retreat;
    if (retreatAction) {
      return retreatAction.targets.includes(slot.index);
    }
    return canRetreatToSlot(retreatSource, slot);
  }

  function startRetreatSelection() {
    if (!focusedSlot || focusedSlot.slot !== 'active') {
      return;
    }
    retreatSource = focusedSlot;
    selectionStore.clearFocus();
  }

  async function resolvePrompt(value: unknown) {
    if (!currentPrompt) return;
    if (gameStore.reviewing) return;
    if (currentPrompt.fields.playbackOnly === true) {
      gameStore.confirmPlaybackPrompt();
      return;
    }
    // One resolve at a time: a duplicated call (double click / stray event) must never
    // reach the engine, where it would be applied to the NEXT pending selection.
    if (gameStore.resolvingPrompt || gameStore.busy) return;
    // The native CABT engine rejects (HTTP 400 → frozen board) any selection whose length is
    // outside [minCount, maxCount] or holds out-of-range / duplicate indexes. Coerce every
    // selection to an engine-legal one before sending so the game can never get stuck.
    const legalized = legalizeCabtSelection(value, currentPrompt);
    const payload = legalized ?? value;
    await gameSessionStore.resolve(() => commandApi.resolvePrompt(currentPrompt.id, payload));
  }

  // Safety net: resolve any prompt with the first legal selection so a card effect can never
  // leave the game stuck, even if its dedicated UI does not render for some board state.
  // Mirrors the CABT reference agent (`list(range(select.maxCount))`).
  // The player must confirm — a card effect's choice is never made silently on their behalf.
  function advanceCurrentPrompt() {
    if (!currentPrompt) return;
    const selection = firstLegalCabtSelection(currentPrompt);
    const cards = extractPromptCards(currentPrompt.fields);
    const names = selection
      .map((optionIndex) => cards.find((card, cardIndex) => (card.index ?? cardIndex) === optionIndex))
      .map((card) => card?.fullName || card?.name)
      .filter((name): name is string => !!name);
    const detail = names.length ? `\n自動で選ばれる候補: ${names.join('、')}` : '';
    if (!window.confirm(`最初の有効な選択肢で自動的に進めます。${detail}\nよろしいですか？`)) {
      return;
    }
    void resolvePrompt(selection);
  }

  function selectHandCard(playerIndex: number, handIndex: number) {
    if (!isSelfControlled(playerIndex)) {
      return;
    }
    if (setupPrompt && playerIndex === setupPrompt.playerIndex) {
      if (!isSetupStartable(game?.players[playerIndex]?.hand[handIndex], handIndex)) {
        return;
      }
      selectionStore.toggleSelectedHand({ playerIndex, handIndex });
      selectionStore.clearFocus();
      return;
    }

    if (!canAct(playerIndex)) {
      return;
    }
    selectionStore.toggleSelectedHand({ playerIndex, handIndex });
    selectionStore.clearFocus();
  }

  function onHandDrag(playerIndex: number, handIndex: number, event: DragEvent) {
    if (!isSelfControlled(playerIndex)) {
      return;
    }
    if (setupPrompt && playerIndex === setupPrompt.playerIndex) {
      if (!isSetupStartable(game?.players[playerIndex]?.hand[handIndex], handIndex)) {
        return;
      }
    } else if (!canAct(playerIndex)) {
      return;
    }
    selectionStore.startDragging({ playerIndex, handIndex });
    event.dataTransfer?.setData('text/plain', `${playerIndex}:${handIndex}`);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
    }
  }

  function clearDragState() {
    selectionStore.clearDragging();
  }

  function allowDrop(event: DragEvent, slot: PokemonSlotView) {
    if (isPlayableTarget(slot) || canPlaceSetupActive(slot) || (attachPrompt && isBoardPromptSelectable(slot))) {
      event.preventDefault();
    }
  }

  function allowBoardPlayDrop(event: DragEvent) {
    if (canPlayOnBoard) {
      event.preventDefault();
    }
  }

  function allowBenchDrop(event: DragEvent, player: PlayerView) {
    if (canPlayToBenchArea(player) || canPlaceSetupBench(player)) {
      event.preventDefault();
    }
  }

  function switchSides() {
    viewSettingsStore.switchToPlayer(topPlayer?.index ?? 0);
  }

  function resetGame() {
    if (replayMode) {
      replayStore.clear();
      resetSaveReplayStatus();
      zoneViewerStore.close();
      viewSettingsStore.resetView();
      homeMode = 'logs';
      if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('view') === 'replay') {
        window.history.replaceState({}, '', window.location.pathname);
      }
      return;
    }
    // Guard against a stray click abandoning a running test match (finished/broken games exit freely).
    if (
      gameStore.game?.ready &&
      !gameStore.gameFinished &&
      !gameStore.error &&
      !window.confirm('対戦を中断してメイン画面に戻りますか？')
    ) {
      return;
    }
    leaveOnlineRoom();
    gameSessionStore.reset();
    resetSaveReplayStatus();
    zoneViewerStore.close();
    viewSettingsStore.resetView();
    boardGlowStore.reset();
    lastAbilityGlowId = -1;
    activePlayerControls = [player1Control, player2Control];
  }

  function resetSaveReplayStatus() {
    saveReplayMessage = '';
    saveReplayError = '';
    savingReplay = false;
  }

  function dropToSlot(slot: PokemonSlotView, event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    clearDragState();
    if (attachPrompt && isBoardPromptSelectable(slot)) {
      assignAttachPromptTarget(slot);
      return;
    }
    if (canPlaceSetupActive(slot)) {
      placeSetupActive();
      return;
    }
    if (isPlayableTarget(slot)) {
      playToSlot(slot);
      return;
    }
  }

  function dropToBoardPlay(event: DragEvent) {
    if (!canPlayOnBoard) {
      return;
    }
    event.preventDefault();
    clearDragState();
    playSelectedToBoard();
  }

  function clickBoardPlay(event: MouseEvent) {
    if (!canPlayOnBoard) {
      return;
    }
    event.preventDefault();
    playSelectedToBoard();
  }

  function dropToBenchArea(player: PlayerView, event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    clearDragState();
    if (canPlaceSetupBench(player)) {
      placeSetupBench();
      return;
    }
    playToBenchArea(player);
  }

  function isPlayableTarget(slot: PokemonSlotView) {
    if (setupPrompt) {
      return false;
    }
    return canPlayCardToSlot(selectedCard, selectedHand?.playerIndex, slot);
  }

  function benchAreaTarget(player: PlayerView) {
    return playableBenchSlot(player, selectedCard, selectedHand?.playerIndex, !!setupPrompt);
  }

  function canPlayToBenchArea(player: PlayerView) {
    if (setupPrompt) {
      return false;
    }
    return !!benchAreaTarget(player);
  }

  function playToBenchArea(player: PlayerView) {
    const target = benchAreaTarget(player);
    if (!target) {
      return;
    }
    playToSlot(target);
  }

  function canPlayToArea(player: PlayerView) {
    if (setupPrompt) {
      return false;
    }
    return canAct(player.index) && canPlayCardToPlayArea(selectedCard, selectedHand?.playerIndex);
  }

  function playSelectedToBoard() {
    if (!game || !activePlayer || !canPlayToArea(activePlayer)) {
      return;
    }
    void playToTarget(targetFor(game.activePlayerIndex, game.activePlayerIndex, SlotType.ACTIVE));
  }

  function showZone(
    playerIndex: number,
    zone: 'discard' | 'lostZone' | 'stadium' | 'playZone',
    title: string,
    faceDown = false,
  ) {
    zoneViewerStore.show(playerIndex, zone, title, faceDown);
  }

  function normalizePromptLimit(value: unknown, fallback: number) {
    return promptLimit(value, fallback);
  }

  function canAct(playerIndex: number) {
    if (replayMode || gameStore.reviewing) {
      return false;
    }
    if (!isSelfControlled(playerIndex)) {
      return false;
    }
    return canPlayerAct({
      playerIndex,
      activePlayerIndex: game?.activePlayerIndex,
      hasPrompt: !!currentPrompt,
      finished: gameFinished,
    });
  }

  function isSelfControlled(playerIndex: number | undefined) {
    return playerIndex === 0 || playerIndex === 1 ? activePlayerControls[playerIndex] === 'self' : false;
  }

  function controlLabel(control: PlayerControl) {
    return control === 'agent' ? 'AI' : '自分';
  }

  function isAttachEnergyAvailable(index: number) {
    const blocked = new Set<number>(promptBlockedIndexes(attachPrompt));
    return isAttachEnergyAvailableModel(index, [...blocked], attachPromptAssignments);
  }

  function canAssignAttachPromptTarget(target: CardTarget, energyIndex = attachPromptEnergyIndex) {
    if (!attachPrompt) {
      return false;
    }
    return canAssignAttachTarget(
      target,
      energyIndex,
      attachPromptAssignments,
      attachPromptTargets,
      attachPromptMax,
      promptOptions(attachPrompt),
      isAttachEnergyAvailable,
    );
  }

  function isBoardPromptSelectable(slot: PokemonSlotView) {
    if (attachPrompt) {
      if (slot.empty) {
        return false;
      }
      const target = targetForPromptSlot(attachPrompt, slot);
      return canAssignAttachPromptTarget(target);
    }
    if (!currentPrompt && canRetreatToSelectedTarget(slot)) {
      return true;
    }
    if (!boardStrategy || !currentPrompt || slot.empty) {
      return false;
    }
    return boardStrategy.isEligible(targetForPromptSlot(currentPrompt, slot));
  }

  function isBoardPromptSelected(slot: PokemonSlotView) {
    if (!currentPrompt && retreatSource) {
      return slot.slot === 'active' && slot.ownerIndex === retreatSource.ownerIndex;
    }
    if (attachPrompt) {
      if (slot.empty) {
        return false;
      }
      const target = targetForPromptSlot(attachPrompt, slot);
      return attachPromptAssignments.some((assignment) => sameTarget(assignment.target, target));
    }
    if (!boardStrategy || !currentPrompt || slot.empty) {
      return false;
    }
    return boardStrategy.isSelected(targetForPromptSlot(currentPrompt, slot));
  }

  function boardSlotDelta(slot: PokemonSlotView) {
    if (!boardStrategy || !currentPrompt || slot.empty) {
      return 0;
    }
    return boardStrategy.deltaFor(targetForPromptSlot(currentPrompt, slot));
  }

  function dispatchBoardClick(slot: PokemonSlotView) {
    if (!currentPrompt && retreatSource) {
      if (canRetreatToSelectedTarget(slot)) {
        void retreat(slot.index);
        return true;
      }
      retreatSource = null;
      return false;
    }
    if (!boardStrategy || !currentPrompt || slot.empty) {
      return false;
    }
    const target = targetForPromptSlot(currentPrompt, slot);
    if (!boardStrategy.isEligible(target)) {
      return false;
    }
    boardStrategy.activate(target);
    return true;
  }

  function clickBoardPromptSlotAtPoint(event: MouseEvent) {
    if (!boardStrategy || resolvingPrompt) {
      return;
    }
    if (event.target instanceof Element && event.target.closest('.prompt-dock, .prompt-strip')) {
      return;
    }
    const slot = boardPromptSlotAtPoint(event.clientX, event.clientY);
    if (!slot || !dispatchBoardClick(slot)) {
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  function boardPromptSlotAtPoint(x: number, y: number) {
    const slotElement = document.elementsFromPoint(x, y).find((element) =>
      element instanceof HTMLElement
        && element.classList.contains('board-slot')
        && element.classList.contains('prompt-selectable'),
    );
    return slotElement instanceof HTMLElement ? boardSlotFromElement(slotElement) : null;
  }

  function boardSlotFromElement(element: HTMLElement): PokemonSlotView | null {
    if (!game) {
      return null;
    }
    const ownerIndex = Number(element.dataset.ownerIndex);
    const slotKind = element.dataset.slotKind;
    const slotIndex = Number(element.dataset.slotIndex);
    const player = game.players.find((item) => item.index === ownerIndex);
    if (!player || !Number.isFinite(slotIndex)) {
      return null;
    }
    if (slotKind === 'active') {
      return player.active;
    }
    if (slotKind === 'bench') {
      return player.bench.find((slot) => slot.index === slotIndex) ?? null;
    }
    return null;
  }

  function assignAttachPromptTarget(slot: PokemonSlotView) {
    if (!attachPrompt || attachPromptEnergyIndex === null || !isBoardPromptSelectable(slot)) {
      return;
    }
    const target = targetForPromptSlot(attachPrompt, slot);
    promptSelectionStore.assignAttachTarget(target, attachPromptMax);
  }

  function selectAttachPromptEnergy(index: number | null) {
    promptSelectionStore.toggleAttachEnergy(index);
  }

  function removeAttachPromptAssignment(index: number) {
    promptSelectionStore.removeAttachAssignment(index);
  }

  function resetAttachPromptAssignments() {
    promptSelectionStore.resetAttachAssignments();
  }

  function isSetupStartable(card: CardView | undefined, handIndex: number) {
    return isSetupStartableModel(card, handIndex, setupBlockedIndexes, !!setupPrompt);
  }

  function selectedSetupHandIndex() {
    return setupPlacementContext.selectedHandIndex;
  }

  function canPlaceSetupActive(slot: PokemonSlotView) {
    return canPlaceSetupActiveModel(slot, setupPlacementContext);
  }

  function placeSetupActive() {
    const handIndex = selectedSetupHandIndex();
    if (handIndex === undefined) {
      return;
    }
    setupSelectionStore.placeActive(handIndex);
    selectionStore.setSelectedHand(null);
  }

  function canPlaceSetupBench(player: PlayerView) {
    return canPlaceSetupBenchModel(player, setupPlacementContext);
  }

  function placeSetupBench() {
    const handIndex = selectedSetupHandIndex();
    if (handIndex === undefined || !setupPlayer || !canPlaceSetupBench(setupPlayer)) {
      return;
    }
    setupSelectionStore.placeBench(handIndex);
    selectionStore.setSelectedHand(null);
  }

  function removeSetupIndex(handIndex: number) {
    setupSelectionStore.remove(handIndex);
  }

  async function confirmSetupPokemon() {
    if (!setupPrompt || !setupCanConfirm) {
      return;
    }
    await resolvePrompt(setupPromptResult(setupHasEngineActive, setupActiveIndex, setupBenchIndexes));
  }

</script>

<svelte:window onkeydown={handleGlobalKeydown} />
<CardZoom />
{#if agentManagerOpen}
  <AgentManagerModal
    profile={activeProfile}
    agents={profileWorkspaceAgents}
    onupload={uploadAgentToProfile}
    ondelete={deleteAgentFromProfile}
    onclose={() => (agentManagerOpen = false)}
  />
{/if}
{#if deckBuilderOpen}
  <DeckBuilderScreen onApply={applyBuiltDeck} onclose={() => (deckBuilderOpen = false)} />
{/if}
{#if showPromptGallery}
  <PromptGallery />
{:else}
<main>
  {#if replayMode && !game}
    <AppHeader />
    <section class="replay-loading-screen">
      <div class="replay-loading-panel">
        <strong>{replayStore.loading ? 'リプレイを読み込み中' : 'リプレイを表示できません'}</strong>
        <span>{replayStore.loading ? 'CABTのリプレイを準備しています。' : labelFor(error || 'リプレイを読み込めませんでした。')}</span>
      </div>
    </section>
  {:else if !game && rematching}
    <AppHeader />
    <section class="replay-loading-screen">
      <div class="replay-loading-panel">
        <strong>再戦を開始しています…</strong>
        <span>同じ設定で新しい対戦を準備しています。</span>
      </div>
    </section>
  {:else if !game && onlineRoom}
    <AppHeader />
    <section class="replay-loading-screen">
      <div class="replay-loading-panel">
        <strong>{onlineWaiting ? '相手の参加を待っています…' : 'オンライン対戦を準備しています…'}</strong>
        <span>
          ルームコード: <strong class="online-code">{onlineRoom.code}</strong>
        </span>
        <span>このコードを相手に伝えて、同じURLの「オンライン対戦」から参加してもらってください。</span>
        <button type="button" onclick={() => leaveOnlineRoom()}>中止して戻る</button>
      </div>
    </section>
  {:else if !game}
    <AppHeader
      onOpenDeckBuilder={() => (deckBuilderOpen = true)}
      {profiles}
      {activeProfile}
      onSelectProfile={(name) => void selectProfile(name)}
      onCreateProfile={(name) => void createNewProfile(name)}
      onImportSamples={() => void importSamplesToProfile()}
      onManageAgents={() => (agentManagerOpen = true)}
    />

      <ImportScreen
        {homeMode}
        bind:deck1Text={deckImportStore.deck1Text}
        bind:deck2Text={deckImportStore.deck2Text}
        bind:player1Control
        bind:player2Control
        bind:player1AgentId
        bind:player2AgentId
        bind:player1DeckSource
        bind:player2DeckSource
        {agents}
        savedDecks={deckBuilderStore.library.map((deck) => ({ id: deck.id, name: deck.name }))}
        {gameLogs}
        player1DeckLocked={player1DeckSource !== 'import'}
        player2DeckLocked={player2DeckSource !== 'import'}
        busy={sessionBusy || player1DeckLoading || player2DeckLoading}
        {catalogBusy}
        {error}
        {catalogError}
        setHomeMode={(nextMode) => {
          homeMode = nextMode;
          if (nextMode === 'logs') {
            activePlayerControls = ['self', 'self'];
            gameStore.reset();
          } else {
            replayStore.clear();
          }
        }}
        startGame={startGame}
        createOnlineRoom={() => void createOnlineRoom()}
        joinOnlineRoom={(code) => void joinOnlineRoom(code)}
        {onlineBusy}
        {loadGameLog}
        refreshCatalog={() => void refreshCatalog()}
      />
  {:else if bottomPlayer && topPlayer}
    <TableShell {debugZones} {replayMode}>
      <GameStatus
        phaseLabel={game.phaseLabel}
        turn={game.turn}
        activePlayerName={activePlayer?.name}
        resultLabel={gameResultLabel}
        modeLabel={replayMode ? '' : modeLabel}
        {gameFinished}
        thinking={!replayMode && sessionBusy && !actingPlayerIsSelf && !playingSequence}
      />

      {#if !replayMode && !gameFinished}
        <TurnBanner
          turn={game.turn}
          activePlayerName={activePlayer?.name}
          activePlayerIndex={game.activePlayerIndex}
          selfIndex={bottomPlayer?.index}
          holdMs={Math.max(viewSettingsStore.actionStepDelayMs, 1400)}
        />
      {/if}

      <Toolbar
        bind:boardTilt={viewSettingsStore.boardTilt}
        bind:boardPerspective={viewSettingsStore.boardPerspective}
        bind:boardScaleY={viewSettingsStore.boardScaleY}
        bind:boardLift={viewSettingsStore.boardLift}
        bind:followActive={viewSettingsStore.followActive}
        bind:autoConfirmPrompts={viewSettingsStore.autoConfirmPrompts}
        bind:debugZones={viewSettingsStore.debugZones}
        bind:showLogs={viewSettingsStore.showLogs}
        bind:showMiniLog={viewSettingsStore.showMiniLog}
        bind:animateActions={viewSettingsStore.animateActions}
        bind:showActionSpotlight={viewSettingsStore.showActionSpotlight}
        bind:revealHands={viewSettingsStore.revealHands}
        bind:actionStepDelayMs={viewSettingsStore.actionStepDelayMs}
        bind:themePreference={viewSettingsStore.themePreference}
        busy={sessionBusy}
        promptActive={replayMode || !!currentPrompt}
        {gameFinished}
        {error}
        {resetPerspective}
        {passTurn}
        {concede}
        {switchSides}
        switchDisabled={!replayMode && actingPlayerIsSelf}
        {resetGame}
        resetLabel={replayMode ? 'リプレイ終了' : 'デッキを変更'}
        reviewing={!replayMode && gameStore.reviewing}
        reviewLabel={gameStore.reviewLabel}
        canStepBack={!replayMode && gameStore.canStepBack}
        stepBack={() => gameStore.stepBack()}
        stepForward={() => gameStore.stepForward()}
        returnToLive={() => gameStore.returnToLive()}
        canUndo={!replayMode && !onlineRoom && gameStore.undoCount > 0}
        undoMove={() => void undoMove()}
        exportLog={() => void exportLog()}
        exporting={exportingLog}
      />

      {#if replayMode && replayStore.replay && replayStore.currentStep}
        <ReplayTimeline
          replay={replayStore.replay}
          step={replayStore.currentStep}
          stepIndex={replayStore.stepIndex}
          copiedForkPoint={replayStore.copiedForkPoint}
          isPlaying={replayStore.isPlaying}
          setStep={(index) => replayStore.setStep(index)}
          setStateIndex={(index) => replayStore.setStateIndex(index)}
          previousStep={() => replayStore.previousStep()}
          nextStep={() => replayStore.nextStep()}
          firstStep={() => replayStore.firstStep()}
          lastStep={() => replayStore.lastStep()}
          togglePlayback={() => replayStore.togglePlayback()}
          backToReplayHome={resetGame}
          copyForkPoint={() => void replayStore.copyForkPoint()}
        />
      {/if}

      {#if gameFinished && !replayMode}
        <EndGamePrompt
          resultLabel={gameResultLabel}
          turn={game.turn}
          onconfirm={resetGame}
          onrematch={() => void rematch(false)}
          onrematchSwapped={() => void rematch(true)}
          rematchDisabled={sessionBusy || savingReplay || player1DeckLoading || player2DeckLoading}
          recordLabel={sessionRecordLabel}
          onsave={() => void saveReplay()}
          saveDisabled={savingReplay || !!saveReplayMessage}
          saveMessage={saveReplayMessage}
          saveError={saveReplayError}
          saving={savingReplay}
        />
      {/if}

      {#if setupPrompt}
        <SetupDock
          needsActive={setupNeedsActive}
          canConfirm={setupCanConfirm}
          resolving={resolvingPrompt}
          confirm={confirmSetupPokemon}
        />
      {:else if boardStrategy}
        <BoardPromptStrip strategy={boardStrategy} resolving={resolvingPrompt} />
      {:else if currentPrompt && !autoResolvePrompt}
        <PromptDock mode={currentPromptDockMode}>
          {#key promptInstanceKey(currentPrompt)}
            <PromptHost
              game={game}
              prompt={currentPrompt}
              resolving={currentPrompt.fields.playbackOnly === true ? false : resolvingPrompt}
              activeAttachEnergyIndex={attachPromptEnergyIndex}
              attachAssignments={attachPromptAssignments}
              onresolve={resolvePrompt}
              onattachEnergySelect={selectAttachPromptEnergy}
              onattachEnergyUnassign={removeAttachPromptAssignment}
              onattachEnergyReset={resetAttachPromptAssignments}
            />
          {/key}
        </PromptDock>
      {/if}

      {#if currentPrompt && !autoResolvePrompt && actingPlayerIsSelf && currentPrompt.fields.playbackOnly !== true && !setupPrompt && !promptHasInteractiveUi(currentPrompt)}
        <button
          class="prompt-safety-advance"
          style="position:fixed; bottom:14px; left:50%; transform:translateX(-50%); z-index:20; padding:7px 14px; border-radius:999px; border:1px solid var(--button-border); background:var(--surface-glass-bg); color:var(--text-secondary); font-size:12px; font-weight:600; cursor:pointer; box-shadow:var(--surface-toolbar-shadow); backdrop-filter:blur(var(--backdrop-blur));"
          onclick={advanceCurrentPrompt}
          disabled={resolvingPrompt}
          title="UIで対象が選べないとき、この選択を最初の有効手で進めます"
        >
          選べない時はここから進める →
        </button>
      {/if}

      {#if onlineOpponentActing}
        <div
          class="online-waiting-hint"
          style="position:fixed; bottom:14px; left:50%; transform:translateX(-50%); z-index:18; padding:8px 16px; border-radius:999px; border:1px solid var(--surface-glass-border); background:var(--surface-glass-bg); color:var(--text-secondary); font-size:13px; font-weight:700; box-shadow:var(--surface-toolbar-shadow); backdrop-filter:blur(var(--backdrop-blur));"
        >⏳ 相手の操作待ち…（ルーム {onlineRoom?.code}）</div>
      {/if}

      {#if error && !gameFinished}
        <div
          class="engine-error-toast"
          role="alert"
          style="position:fixed; top:64px; left:50%; transform:translateX(-50%); z-index:40; display:flex; align-items:center; gap:12px; max-width:min(92vw,560px); padding:10px 14px; border-radius:12px; border:1px solid var(--danger-border); background:var(--danger-bg); color:var(--danger-strong); font-size:13px; font-weight:700; box-shadow:var(--surface-toolbar-shadow); backdrop-filter:blur(var(--backdrop-blur));"
        >
          <span style="min-width:0; overflow-wrap:anywhere;">{labelFor(error)}</span>
          <button
            type="button"
            onclick={() => gameStore.setError('')}
            aria-label="エラーを閉じる"
            style="flex:0 0 auto; border:0; background:transparent; color:inherit; font-size:15px; line-height:1; cursor:pointer; padding:2px 4px;"
          >✕</button>
        </div>
      {/if}

      {#if !replayMode && viewSettingsStore.showActionSpotlight}
        <ActionSpotlight
          timeline={game.actionTimeline}
          holdMs={Math.max(viewSettingsStore.actionStepDelayMs, 1400)}
        />
      {/if}

      {#if !replayMode}
        <DrawFlyIn timeline={game.actionTimeline} selfIndex={bottomPlayer?.index} />
      {/if}

      <BoardLayer>
        <PlayerPanel side="top">
          <Hand
            player={topPlayer}
            selectedHand={selectedHand}
            disabled={!isSelfControlled(topPlayer.index) || (!canAct(topPlayer.index) && setupPrompt?.playerIndex !== topPlayer.index)}
            playableIndexes={setupPrompt?.playerIndex === topPlayer.index ? setupPlayableIndexes : []}
            placedIndexes={setupPrompt?.playerIndex === topPlayer.index ? setupPlacedIndexes : []}
            concealed={!revealHands
              && (!isSelfControlled(topPlayer.index)
                || (bothPlayersSelf && topPlayer.index !== actingPlayerIndex))}
            sortable={isSelfControlled(topPlayer.index)}
            sorted={viewSettingsStore.sortHand}
            onToggleSort={() => (viewSettingsStore.sortHand = !viewSettingsStore.sortHand)}
            onSelect={selectHandCard}
            onDrag={onHandDrag}
            onDragEnd={clearDragState}
          />
        </PlayerPanel>

        <GameBoard
          {topPlayer}
          {bottomPlayer}
          {topBenchSlots}
          {bottomBenchSlots}
          {topActiveSlot}
          {bottomActiveSlot}
          {currentStadium}
          {currentStadiumOwner}
          {canPlayToBenchArea}
          {canPlaceSetupBench}
          {playToBenchArea}
          {placeSetupBench}
          {allowBenchDrop}
          {dropToBenchArea}
          {isPlayableTarget}
          {isBoardPromptSelectable}
          {isBoardPromptSelected}
          {boardSlotDelta}
          {clickSlot}
          {allowDrop}
          {dropToSlot}
          {canPlaceSetupActive}
          {placeSetupActive}
          {showZone}
          {canPlayOnBoard}
          {clickBoardPlay}
          {allowBoardPlayDrop}
          {dropToBoardPlay}
          {boardTilt}
          {boardPerspective}
          {boardScaleY}
          {boardLift}
        />

        <PlayerPanel side="bottom">
          <Hand
            player={bottomPlayer}
            selectedHand={selectedHand}
            disabled={!isSelfControlled(bottomPlayer.index) || (!canAct(bottomPlayer.index) && setupPrompt?.playerIndex !== bottomPlayer.index)}
            playableIndexes={setupPrompt?.playerIndex === bottomPlayer.index ? setupPlayableIndexes : []}
            placedIndexes={setupPrompt?.playerIndex === bottomPlayer.index ? setupPlacedIndexes : []}
            concealed={!revealHands && !isSelfControlled(bottomPlayer.index)}
            sortable={isSelfControlled(bottomPlayer.index)}
            sorted={viewSettingsStore.sortHand}
            onToggleSort={() => (viewSettingsStore.sortHand = !viewSettingsStore.sortHand)}
            onSelect={selectHandCard}
            onDrag={onHandDrag}
            onDragEnd={clearDragState}
          />
        </PlayerPanel>

        {#if focusedSlot}
          <ActiveFocus
            slot={focusedSlot}
            availableActions={focusedPlayer?.availableActions}
            benchTargets={focusedBenchTargets}
            busy={sessionBusy}
            promptActive={!!currentPrompt}
            canAct={focusedCanAct}
            {canRetreatToSlot}
            close={() => {
              selectionStore.clearFocus();
            }}
            {useAbility}
            {attack}
            startRetreat={startRetreatSelection}
          />
        {/if}

        {#if showLogs}
          <LogPanel logs={game.logs} timeline={game.actionTimeline} />
        {:else if viewSettingsStore.showMiniLog}
          <LogTicker
            logs={game.logs}
            timeline={game.actionTimeline}
            onHide={() => (viewSettingsStore.showMiniLog = false)}
          />
        {/if}

        <ZoneViewer
          open={zoneViewerOpen}
          title={zoneViewerTitle}
          cards={viewedCards}
          faceDown={zoneViewerFaceDown}
          actionLabel={zoneViewerIsStadium && viewedCards.length ? 'スタジアムを使う' : ''}
          actionDisabled={sessionBusy || !!currentPrompt || gameFinished || replayMode || gameStore.reviewing}
          actionTitle='このスタジアムの「1ターンに1回」効果を使う'
          onAction={useStadium}
          close={() => zoneViewerStore.close()}
        />
      </BoardLayer>
    </TableShell>
  {:else}
    <AppHeader />
    <section class="replay-loading-screen">
      <div class="replay-loading-panel">
        <strong>ゲームを開始できません</strong>
        <span>{labelFor(error || game.logs.at(-1)?.message || 'エンジンが不正な開始前の状態を返しました。')}</span>
        <button type="button" onclick={resetGame}>デッキを変更</button>
      </div>
    </section>
  {/if}
</main>
{/if}

<style>
  .replay-loading-screen {
    min-height: 100vh;
    display: grid;
    align-content: center;
    justify-content: center;
    padding: 72px 24px 24px;
  }

  .replay-loading-panel {
    display: grid;
    gap: 8px;
    width: min(420px, calc(100vw - 32px));
    padding: 16px;
    border-radius: 8px;
    border: 1px solid rgba(26, 31, 39, 0.16);
    background: #f7f8fa;
    color: #1d232b;
    box-shadow: 0 12px 32px rgba(12, 15, 19, 0.18);
  }

  .replay-loading-panel strong {
    font-size: 14px;
  }

  .replay-loading-panel span {
    color: #566272;
    font-size: 13px;
  }

</style>
