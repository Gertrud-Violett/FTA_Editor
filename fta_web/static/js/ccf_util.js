/**
 * ccf_util.js -- pure helpers for the CCF groups (F2), shared by tree.js,
 * details.js, tabs/cutsets.js, tabs/importance.js and main.js. No DOM and no
 * imports, so every function can be read (and tested) on its own.
 *
 * The groups live in the document's analysis as `analysis.ccfGroups` (a list
 * of `{id, name, model, beta, alpha, testing, members, source}`); a document
 * without a group has no such key, and every helper then answers "nothing".
 */

/** The stored groups that are objects with a usable id; [] when there is none. */
export function groupsOf(analysis) {
  const list = analysis && Array.isArray(analysis.ccfGroups) ? analysis.ccfGroups : [];
  return list.filter((g) => g && typeof g === 'object' && typeof g.id === 'string' && g.id !== '');
}

/** The distinct member ids of a group, in order (anything but a non-empty string is left out). */
export function membersOfGroup(group) {
  const members = group && Array.isArray(group.members) ? group.members : [];
  const seen = new Set();
  const out = [];
  for (const m of members) {
    if (typeof m === 'string' && m !== '' && !seen.has(m)) {
      seen.add(m);
      out.push(m);
    }
  }
  return out;
}

/** A group's display name (its id when the name is not text). */
export function groupName(group) {
  return group && typeof group.name === 'string' && group.name !== '' ? group.name : String(group && group.id);
}

const memberCache = { analysis: null, map: null };

/** Map member id -> [{id, name}] over every stored group (cached per analysis object). */
export function memberMap(analysis) {
  if (memberCache.analysis === analysis && memberCache.map) return memberCache.map;
  const map = new Map();
  for (const group of groupsOf(analysis)) {
    for (const member of membersOfGroup(group)) {
      if (!map.has(member)) map.set(member, []);
      map.get(member).push({ id: group.id, name: groupName(group) });
    }
  }
  memberCache.analysis = analysis;
  memberCache.map = map;
  return map;
}

/**
 * The text of a cut-set or importance event: `CCF: <group>` for the CCF event of
 * a beta group, `CCF: <group> (A + B)` for the event of an alpha-factor subset
 * (its marker carries `memberNames`), `<name> (independent part)` for the
 * independent part of a member, the event's own name otherwise. `t` is the
 * shell's translator.
 */
export function eventLabel(ev, t) {
  const fallback = ev && (ev.name || ev.id) !== undefined ? String(ev.name || ev.id) : '';
  const marker = ev && ev.ccf && typeof ev.ccf === 'object' ? ev.ccf : null;
  if (!marker || typeof t !== 'function') return fallback;
  const base = marker.baseName === undefined || marker.baseName === null ? '' : String(marker.baseName);
  if (marker.role === 'event' && Array.isArray(marker.memberNames)) {
    return t('ccf.label.subset', { name: base, members: marker.memberNames.join(' + ') });
  }
  if (marker.role === 'event') return t('ccf.label.event', { name: base });
  if (marker.role === 'independent') return t('ccf.label.independent', { name: base });
  return fallback;
}

/**
 * The tree nodes a cut-set event stands for: the members of the group for the
 * CCF event, the event's own id for anything else (the independent part carries
 * its member's id).
 */
export function membersOfEvent(ev) {
  const marker = ev && ev.ccf && typeof ev.ccf === 'object' ? ev.ccf : null;
  if (marker && marker.role === 'event' && Array.isArray(marker.members) && marker.members.length) {
    return marker.members.map(String);
  }
  return [String(ev && ev.id)];
}

const ancestorCache = { tree: null, analysis: null, set: null };

/**
 * The ids of the nodes that have a CCF member below them (any group, applied
 * or not): the gates whose cut-set value may differ from the tree walk. A leaf
 * whose links point at a member (or at such a node) counts as a gate too, as
 * does a transfer gate whose target is one, and a member that has a link to a
 * node of the tree (FN-66). Used to show a dash instead of a tree-walk number while the CCF
 * state is loading.
 */
export function ancestorsOfMembers(tree, analysis) {
  if (ancestorCache.tree === tree && ancestorCache.analysis === analysis && ancestorCache.set) {
    return ancestorCache.set;
  }
  const wanted = memberMap(analysis);
  const out = new Set();
  if (wanted.size) {
    const nodes = [];
    const collect = (node) => {
      if (!node || typeof node !== 'object') return;
      nodes.push(node);
      for (const child of Array.isArray(node.children) ? node.children : []) collect(child);
    };
    collect(tree);
    const ids = new Set(nodes.map((node) => String(node.id)));
    const reaches = (id) => wanted.has(id) || out.has(id);
    let changed = true;
    while (changed) {
      changed = false;
      for (const node of nodes) {
        const id = String(node.id);
        if (out.has(id)) continue;
        const kids = Array.isArray(node.children) ? node.children : [];
        const links = Array.isArray(node.links) ? node.links : [];
        const hop = node.transferTo === undefined || node.transferTo === null || node.transferTo === '' ? null : String(node.transferTo);
        // A member that has a link to a node of the tree is itself such a gate (FN-66):
        // its value is the cut-set value, not the tree walk. Other nodes are one when
        // a child, a link target or a transfer target is a member or such a gate.
        const below =
          kids.some((child) => child && reaches(String(child.id))) ||
          links.some((link) => link && link.target_id && reaches(String(link.target_id))) ||
          (hop !== null && reaches(hop)) ||
          (wanted.has(id) && links.some((link) => link && link.target_id && ids.has(String(link.target_id))));
        if (below) {
          out.add(id);
          changed = true;
        }
      }
    }
  }
  ancestorCache.tree = tree;
  ancestorCache.analysis = analysis;
  ancestorCache.set = out;
  return out;
}
