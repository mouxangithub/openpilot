import {
  AnimationClip,
  AnimationMixer,
  Matrix4,
  Quaternion,
  QuaternionKeyframeTrack,
  SkeletonHelper,
  Vector3,
  VectorKeyframeTrack,
} from '../../../three.module.js';

function getBoneName(bone, options) {
  if (options.getBoneName !== undefined) return options.getBoneName(bone);
  return options.names[bone.name];
}

function getBoneByName(name, skeleton) {
  for (let i = 0, bones = getBones(skeleton); i < bones.length; i += 1) {
    if (name === bones[i].name) return bones[i];
  }
  return null;
}

function getBones(skeleton) {
  return Array.isArray(skeleton) ? skeleton : skeleton.bones;
}

function getHelperFromSkeleton(skeleton) {
  const source = new SkeletonHelper(skeleton.bones[0]);
  source.skeleton = skeleton;
  return source;
}

function parallelTraverse(a, b, callback) {
  callback(a, b);
  for (let i = 0; i < a.children.length; i += 1) {
    parallelTraverse(a.children[i], b.children[i], callback);
  }
}

function clone(source) {
  const sourceLookup = new Map();
  const cloneLookup = new Map();
  const cloned = source.clone();
  parallelTraverse(source, cloned, (sourceNode, clonedNode) => {
    sourceLookup.set(clonedNode, sourceNode);
    cloneLookup.set(sourceNode, clonedNode);
  });
  cloned.traverse((node) => {
    if (!node.isSkinnedMesh) return;
    const clonedMesh = node;
    const sourceMesh = sourceLookup.get(node);
    const sourceBones = sourceMesh.skeleton.bones;
    clonedMesh.skeleton = sourceMesh.skeleton.clone();
    clonedMesh.bindMatrix.copy(sourceMesh.bindMatrix);
    clonedMesh.skeleton.bones = sourceBones.map((bone) => cloneLookup.get(bone));
    clonedMesh.bind(clonedMesh.skeleton, clonedMesh.bindMatrix);
  });
  return cloned;
}

function retarget(target, source, options = {}) {
  const quat = new Quaternion();
  const scale = new Vector3();
  const relativeMatrix = new Matrix4();
  const globalMatrix = new Matrix4();
  options.preserveBoneMatrix = options.preserveBoneMatrix !== undefined ? options.preserveBoneMatrix : true;
  options.preserveBonePositions = options.preserveBonePositions !== undefined ? options.preserveBonePositions : true;
  options.useTargetMatrix = options.useTargetMatrix !== undefined ? options.useTargetMatrix : false;
  options.hip = options.hip !== undefined ? options.hip : 'hip';
  options.hipInfluence = options.hipInfluence !== undefined ? options.hipInfluence : new Vector3(1, 1, 1);
  options.scale = options.scale !== undefined ? options.scale : 1;
  options.names = options.names || {};
  const sourceBones = source.isObject3D ? source.skeleton.bones : getBones(source);
  const bones = target.isObject3D ? target.skeleton.bones : getBones(target);
  let bone;
  let name;
  let boneTo;
  let bonesPosition;
  if (target.isObject3D) target.skeleton.pose();
  else {
    options.useTargetMatrix = true;
    options.preserveBoneMatrix = false;
  }
  if (options.preserveBonePositions) {
    bonesPosition = [];
    for (let i = 0; i < bones.length; i += 1) bonesPosition.push(bones[i].position.clone());
  }
  if (options.preserveBoneMatrix) {
    target.updateMatrixWorld();
    target.matrixWorld.identity();
    for (let i = 0; i < target.children.length; i += 1) target.children[i].updateMatrixWorld(true);
  }
  for (let i = 0; i < bones.length; i += 1) {
    bone = bones[i];
    name = getBoneName(bone, options);
    boneTo = getBoneByName(name, sourceBones);
    globalMatrix.copy(bone.matrixWorld);
    if (boneTo) {
      boneTo.updateMatrixWorld();
      if (options.useTargetMatrix) relativeMatrix.copy(boneTo.matrixWorld);
      else {
        relativeMatrix.copy(target.matrixWorld).invert();
        relativeMatrix.multiply(boneTo.matrixWorld);
      }
      scale.setFromMatrixScale(relativeMatrix);
      relativeMatrix.scale(scale.set(1 / scale.x, 1 / scale.y, 1 / scale.z));
      globalMatrix.makeRotationFromQuaternion(quat.setFromRotationMatrix(relativeMatrix));
      globalMatrix.copyPosition(relativeMatrix);
    }
    if (name === options.hip) {
      globalMatrix.elements[12] *= options.scale * options.hipInfluence.x;
      globalMatrix.elements[13] *= options.scale * options.hipInfluence.y;
      globalMatrix.elements[14] *= options.scale * options.hipInfluence.z;
    }
    if (bone.parent) {
      bone.matrix.copy(bone.parent.matrixWorld).invert();
      bone.matrix.multiply(globalMatrix);
    } else bone.matrix.copy(globalMatrix);
    bone.matrix.decompose(bone.position, bone.quaternion, bone.scale);
    bone.updateMatrixWorld();
  }
  if (options.preserveBonePositions) {
    for (let i = 0; i < bones.length; i += 1) {
      bone = bones[i];
      name = getBoneName(bone, options) || bone.name;
      if (name !== options.hip) bone.position.copy(bonesPosition[i]);
    }
  }
  if (options.preserveBoneMatrix) target.updateMatrixWorld(true);
}

function retargetClip(target, source, clip, options = {}) {
  options.useFirstFramePosition = options.useFirstFramePosition !== undefined ? options.useFirstFramePosition : false;
  options.fps = options.fps !== undefined ? options.fps : (Math.max(...clip.tracks.map((track) => track.times.length)) / clip.duration);
  options.names = options.names || [];
  if (!source.isObject3D) source = getHelperFromSkeleton(source);
  const numFrames = Math.round(clip.duration * (options.fps / 1000) * 1000);
  const delta = clip.duration / (numFrames - 1);
  const convertedTracks = [];
  const mixer = new AnimationMixer(source);
  const bones = getBones(target.skeleton);
  const boneDatas = [];
  mixer.clipAction(clip).play();
  let start = 0;
  let end = numFrames;
  if (options.trim !== undefined) {
    start = Math.round(options.trim[0] * options.fps);
    end = Math.min(Math.round(options.trim[1] * options.fps), numFrames) - start;
    mixer.update(options.trim[0]);
  } else mixer.update(0);
  source.updateMatrixWorld();
  for (let frame = 0; frame < end; frame += 1) {
    const time = frame * delta;
    retarget(target, source, options);
    for (let j = 0; j < bones.length; j += 1) {
      const b = bones[j];
      const bname = getBoneName(b, options) || b.name;
      const bTo = getBoneByName(bname, source.skeleton);
      if (bTo) {
        let boneData = boneDatas[j];
        if (!boneData) boneData = boneDatas[j] = { bone: b };
        if (!boneData.quat) {
          boneData.quat = { times: new Float32Array(end), values: new Float32Array(end * 4) };
        }
        boneData.quat.times[frame] = time;
        b.quaternion.toArray(boneData.quat.values, frame * 4);
      }
    }
    if (frame === end - 2) mixer.update(delta - 0.0000001);
    else mixer.update(delta);
    source.updateMatrixWorld();
  }
  for (let i = 0; i < boneDatas.length; i += 1) {
    const boneData = boneDatas[i];
    if (!boneData) continue;
    convertedTracks.push(new QuaternionKeyframeTrack(
      `.bones[${boneData.bone.name}].quaternion`,
      boneData.quat.times,
      boneData.quat.values,
    ));
  }
  mixer.uncacheAction(clip);
  return new AnimationClip(clip.name, -1, convertedTracks);
}

export { retarget, retargetClip, clone };
