/** Keep explicit and saved selections ahead of the default goal fallback. */
export function chooseRoadmap(items, {targetId, currentId, storedId, goal, goalWasChosen}) {
  const roads = Array.isArray(items) ? items : [];
  if (targetId != null) return roads.find(item => item?.id === targetId) ?? null;
  const preferred = roads.find(item => item?.id === (currentId ?? storedId)
    && (!goalWasChosen || item.goal === goal));
  if (preferred) return preferred;
  const nonempty = item => Array.isArray(item?.milestones) && item.milestones.length > 0;
  return roads.find(item => item?.goal === goal && nonempty(item))
    ?? roads.find(item => item?.goal === goal)
    ?? (goalWasChosen ? null : roads.find(nonempty) ?? roads[0] ?? null);
}

export function chooseMilestone(items, previousId, storedId) {
  const milestones = Array.isArray(items) ? items : [];
  return milestones.find(item => item.id === previousId)?.id
    ?? milestones.find(item => item.id === storedId)?.id
    ?? milestones[0]?.id ?? null;
}
