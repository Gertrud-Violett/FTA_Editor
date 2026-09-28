/**
 * schema.js -- node-schema constants shared by every 1.7 frontend module.
 * Mirrors fta_web/node_schema.py; keep the two in step.
 *
 * All new node keys are optional. A node without them behaves exactly as a
 * 1.6 node: `logicGate` AND/OR, a basic event, a fixed probability.
 */

/** Every gate kind the 1.7 engine understands (stored in `gateType`). */
export const GATE_TYPES = Object.freeze(['AND', 'OR', 'KOFN', 'XOR', 'INHIBIT', 'PAND', 'TRANSFER']);

/** The gates basic mode, the desktop app and `logicGate` accept. */
export const BASIC_GATES = Object.freeze(['AND', 'OR']);

/** `eventKind` values. */
export const EVENT_KINDS = Object.freeze(['basic', 'house', 'undeveloped', 'conditioning']);

/** `quant.model` values. */
export const QUANT_MODELS = Object.freeze(['fixed', 'rate', 'standby', 'repairable']);

/** `trace.status` values. */
export const TRACE_STATUS = Object.freeze(['draft', 'reviewed', 'approved']);

const AND_LIKE = new Set(['AND', 'INHIBIT', 'PAND']);

/**
 * The AND/OR a gate type is projected to in `logicGate`, which the AI
 * validator and the desktop editor still read. AND, INHIBIT and PAND are
 * AND-like; everything else (OR, KOFN, XOR, TRANSFER, unknown) is OR.
 */
export function projectLogicGate(gateType) {
  const gate = String(gateType === null || gateType === undefined ? '' : gateType)
    .trim()
    .toUpperCase();
  return AND_LIKE.has(gate) ? 'AND' : 'OR';
}

function nonEmptyObject(value) {
  if (!value || typeof value !== 'object') return false;
  return Object.keys(value).some((key) => {
    const v = value[key];
    if (v === null || v === undefined || v === '') return false;
    if (Array.isArray(v)) return v.length > 0;
    return true;
  });
}

/**
 * True when a node uses anything basic mode does not edit: a gate other than
 * AND/OR, a non-basic event kind, a non-fixed quantification model, or
 * traceability / FMEA data. Basic mode shows such nodes read-only with an
 * "advanced" chip rather than hiding or dropping anything.
 */
export function isAdvancedNode(node) {
  if (!node || typeof node !== 'object') return false;
  const gateType = node.gateType;
  if (gateType !== undefined && gateType !== null && gateType !== '') {
    if (BASIC_GATES.indexOf(String(gateType).trim().toUpperCase()) === -1) return true;
  }
  const kind = node.eventKind;
  if (kind !== undefined && kind !== null && kind !== '' && String(kind).toLowerCase() !== 'basic') {
    return true;
  }
  const quant = node.quant;
  if (quant && typeof quant === 'object') {
    const model = quant.model;
    if (model !== undefined && model !== null && model !== '' && String(model).toLowerCase() !== 'fixed') {
      return true;
    }
  }
  if (nonEmptyObject(node.trace)) return true;
  if (nonEmptyObject(node.fmea)) return true;
  return false;
}
