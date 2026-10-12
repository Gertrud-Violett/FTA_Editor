/**
 * i18n/fix181.js -- strings for the fixes of the known issues of 1.8.0: Stop
 * in the assistant freeing the editor's AI slot, the recovery copy of unsaved
 * work offered at start-up, and choosing the allowed folder while the editor
 * runs.
 *
 * Catalog format (parsed by fta_web/tests/test_catalog_parity.py, so keep it
 * flat, single-quoted, one entry per line): `export default { en: {...},
 * ja: {...} };`. main.js registerStrings() merges it into STRINGS. Keys must
 * not collide with main.js or any other catalog; the parity test enforces it.
 */
export default {
  en: {
    'ai.msg.stopNotFreed': 'The editor could not be told to abandon that request. Until the provider answers, a new request may be refused as busy.',
  },
  ja: {
    'ai.msg.stopNotFreed': 'エディターにこの要求の破棄を伝えられませんでした。プロバイダーから回答が返るまで、新しい要求が処理中として拒否されることがあります。',
  },
};
