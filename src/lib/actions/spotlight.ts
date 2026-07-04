// カーソル位置をCSS変数(--sx/--sy)で要素に渡す表示専用アクション。
// 各コンポーネント側の ::after radial-gradient と組で「枠のスポットライト」になる。
export function spotlight(node: HTMLElement) {
  const onMove = (event: MouseEvent) => {
    const rect = node.getBoundingClientRect();
    node.style.setProperty('--sx', `${event.clientX - rect.left}px`);
    node.style.setProperty('--sy', `${event.clientY - rect.top}px`);
  };
  node.addEventListener('mousemove', onMove);
  return { destroy: () => node.removeEventListener('mousemove', onMove) };
}
