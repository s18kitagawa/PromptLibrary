/**
 * 3年以上前のGmailスレッドをゴミ箱に移動するスクリプト
 *
 * ※重要マーク付きのスレッドも削除対象に含む
 *
 * 対象外:
 *  - スター付きのメールを含むスレッド
 *  - スレッドの最新メールの受信日が3年未満のもの
 */

const CONFIG = {
  YEARS: 3,                        // 何年以上前を対象にするか
  BATCH_SIZE: 100,                 // 1回の検索で取得する件数（最大100）
  MAX_RUNTIME_MS: 5 * 60 * 1000,   // 実行時間の上限（GASの6分制限より手前で止める）
  DRY_RUN: true,                   // true: ログ出力のみで削除しない / false: 実際にゴミ箱へ移動
};

function trashOldThreads() {
  const startTime = Date.now();

  // 基準日（今日からN年前）
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - CONFIG.YEARS);

  // 検索条件で大まかに絞り込み、細かい判定はコード側で行う
  const query = `older_than:${CONFIG.YEARS}y -is:starred -in:trash -in:spam`;

  let offset = 0;
  let trashedCount = 0;
  let skippedCount = 0;

  while (Date.now() - startTime < CONFIG.MAX_RUNTIME_MS) {
    const threads = GmailApp.search(query, offset, CONFIG.BATCH_SIZE);
    if (threads.length === 0) break;

    const targets = [];

    for (const thread of threads) {
      const isRecent = thread.getLastMessageDate() >= cutoff; // 最新メールが3年未満
      const hasStar = thread.hasStarredMessages();            // スレッド内にスター付きあり

      if (isRecent || hasStar) {
        skippedCount++;
        continue;
      }
      targets.push(thread);
    }

    if (targets.length > 0) {
      if (CONFIG.DRY_RUN) {
        targets.forEach(t =>
          console.log(`[DRY RUN] ${t.getLastMessageDate().toLocaleDateString()} ${t.getFirstMessageSubject()}`)
        );
      } else {
        GmailApp.moveThreadsToTrash(targets);
      }
      trashedCount += targets.length;
    }

    // ゴミ箱に移動したスレッドは次の検索結果から消えるため、
    // 除外したスレッドの分だけ読み取り位置を進める
    offset += CONFIG.DRY_RUN ? threads.length : threads.length - targets.length;

    if (threads.length < CONFIG.BATCH_SIZE) break;
  }

  const mode = CONFIG.DRY_RUN ? '（DRY RUN：実際には移動していません）' : '';
  console.log(`完了${mode} ゴミ箱へ移動: ${trashedCount}件 / 除外: ${skippedCount}件`);
}

/**
 * 毎月1日の午前3時台に自動実行するトリガーを設定する（初回に1回だけ実行）
 * ※既存の trashOldThreads 用トリガーは削除してから作り直す
 */
function setupMonthlyTrigger() {
  // 重複を防ぐため、既存の同名トリガーを削除
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'trashOldThreads')
    .forEach(t => ScriptApp.deleteTrigger(t));

  ScriptApp.newTrigger('trashOldThreads')
    .timeBased()
    .onMonthDay(1)
    .atHour(3)
    .create();

  console.log('毎月1日の午前3時台に実行するトリガーを設定しました');
}
