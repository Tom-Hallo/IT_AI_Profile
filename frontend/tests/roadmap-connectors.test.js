import assert from 'node:assert/strict';
import test from 'node:test';
import {connectorPath,connectorPoints} from '../src/pixel-studio/roadmap-connectors.js';

test('horizontal map keeps the original two elbow positions and endpoints', () => {
  const from = {x:40,y:90};
  const to = {x:240,y:150};
  const points = connectorPoints(from,to,false);
  assert.deepEqual(points,[from,{x:140,y:90},{x:140,y:150},to]);
  assert.equal(connectorPath(points),'M40 90 L140 90 L140 150 L240 150');
});

test('vertical map keeps the original two elbow positions and endpoints', () => {
  const from = {x:80,y:50};
  const to = {x:200,y:250};
  const points = connectorPoints(from,to,true);
  assert.deepEqual(points,[from,{x:80,y:150},{x:200,y:150},to]);
  assert.equal(connectorPath(points),'M80 50 L80 150 L200 150 L200 250');
});

test('resizing the map or Mentor panel recalculates connectors from current node centers', () => {
  const original = connectorPath(connectorPoints({x:50,y:60},{x:250,y:160},false));
  const resized = connectorPath(connectorPoints({x:30,y:60},{x:150,y:160},false));
  assert.equal(resized,'M30 60 L90 60 L90 160 L150 160');
  assert.notEqual(resized,original);
});

test('path calculation does not mutate node positions or statuses', () => {
  const from = Object.freeze({x:20,y:30,status:'completed'});
  const to = Object.freeze({x:90,y:60,status:'pending'});
  connectorPath(connectorPoints(from,to,false));
  assert.equal(from.status,'completed');
  assert.equal(to.status,'pending');
});
