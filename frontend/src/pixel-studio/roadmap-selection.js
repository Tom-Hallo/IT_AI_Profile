/** Keep explicit and saved selections ahead of the default goal fallback. */
export function chooseRoadmap(items, {targetId, currentId, storedId, goal, goalWasChosen}) {
  const roads = Array.isArray(items) ? items : [];
  if (targetId != null) return roads.find(item => item?.id === targetId) ?? null;
  const preferred = [currentId, storedId]
    .filter(id => id != null)
    .map(id => roads.find(item => item?.id === id && (!goalWasChosen || item.goal === goal)))
    .find(Boolean);
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

/** Resolve the whole view before committing any UI state. A missing focus falls
 * back to a valid selection, using only tracking fetched for that roadmap. */
export async function resolveRoadmapView(items, options, loadTracking, readStoredMilestone) {
  let roads = Array.isArray(items) ? items : [];
  const {pendingFocus, previousMilestone} = options;
  let focusError = null;
  let focusedRoad = null;
  let focusedTracking = null;
  if (pendingFocus) {
    focusedRoad = roads.find(item => String(item?.id) === String(pendingFocus.roadmapId));
    if (focusedRoad) {
      try {
        focusedTracking = await loadTracking(focusedRoad.id);
      } catch (error) {
        if (error.status !== 404) throw error;
        roads = roads.filter(item => item?.id !== focusedRoad.id);
        focusedRoad = null;
      }
    }
    if (!focusedRoad) {
      focusError = 'roadmap';
    } else {
      const milestones = Array.isArray(focusedTracking?.milestones) ? focusedTracking.milestones : [];
      const milestone = milestones.find(item => String(item?.id) === String(pendingFocus.milestoneId));
      if (milestone) {
        return {roads, road:focusedRoad, tracking:focusedTracking, milestone:milestone.id, focusError:null};
      }
      focusError = 'milestone';
    }
  }
  const road = chooseRoadmap(roads, options);
  const tracking = road
    ? (road.id === focusedRoad?.id ? focusedTracking : await loadTracking(road.id))
    : null;
  const milestone = road ? chooseMilestone(
    tracking?.milestones,
    road.id === options.currentId ? previousMilestone : null,
    readStoredMilestone(road.id)
  ) : null;
  return {roads, road, tracking, milestone, focusError};
}
