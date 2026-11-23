// Keep canvas and SVG connectors on the same orthogonal route.
export function connectorPoints(from,to,vertical) {
  if (vertical) {
    const middleY = (from.y + to.y) / 2;
    return [from,{x:from.x,y:middleY},{x:to.x,y:middleY},to];
  }
  const middleX = (from.x + to.x) / 2;
  return [from,{x:middleX,y:from.y},{x:middleX,y:to.y},to];
}

export function connectorPath(points) {
  return points.map(({x,y},index) => (index ? 'L' : 'M') + x + ' ' + y).join(' ');
}
