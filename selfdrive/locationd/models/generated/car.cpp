#include "car.h"

namespace {
#define DIM 9
#define EDIM 9
#define MEDIM 9
typedef void (*Hfun)(double *, double *, double *);

double mass;

void set_mass(double x){ mass = x;}

double rotational_inertia;

void set_rotational_inertia(double x){ rotational_inertia = x;}

double center_to_front;

void set_center_to_front(double x){ center_to_front = x;}

double center_to_rear;

void set_center_to_rear(double x){ center_to_rear = x;}

double stiffness_front;

void set_stiffness_front(double x){ stiffness_front = x;}

double stiffness_rear;

void set_stiffness_rear(double x){ stiffness_rear = x;}
const static double MAHA_THRESH_25 = 3.8414588206941227;
const static double MAHA_THRESH_24 = 5.991464547107981;
const static double MAHA_THRESH_30 = 3.8414588206941227;
const static double MAHA_THRESH_26 = 3.8414588206941227;
const static double MAHA_THRESH_27 = 3.8414588206941227;
const static double MAHA_THRESH_29 = 3.8414588206941227;
const static double MAHA_THRESH_28 = 3.8414588206941227;
const static double MAHA_THRESH_31 = 3.8414588206941227;

/******************************************************************************
 *                       Code generated with SymPy 1.12                       *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_1086654683844306915) {
   out_1086654683844306915[0] = delta_x[0] + nom_x[0];
   out_1086654683844306915[1] = delta_x[1] + nom_x[1];
   out_1086654683844306915[2] = delta_x[2] + nom_x[2];
   out_1086654683844306915[3] = delta_x[3] + nom_x[3];
   out_1086654683844306915[4] = delta_x[4] + nom_x[4];
   out_1086654683844306915[5] = delta_x[5] + nom_x[5];
   out_1086654683844306915[6] = delta_x[6] + nom_x[6];
   out_1086654683844306915[7] = delta_x[7] + nom_x[7];
   out_1086654683844306915[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_1205985898548646392) {
   out_1205985898548646392[0] = -nom_x[0] + true_x[0];
   out_1205985898548646392[1] = -nom_x[1] + true_x[1];
   out_1205985898548646392[2] = -nom_x[2] + true_x[2];
   out_1205985898548646392[3] = -nom_x[3] + true_x[3];
   out_1205985898548646392[4] = -nom_x[4] + true_x[4];
   out_1205985898548646392[5] = -nom_x[5] + true_x[5];
   out_1205985898548646392[6] = -nom_x[6] + true_x[6];
   out_1205985898548646392[7] = -nom_x[7] + true_x[7];
   out_1205985898548646392[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_5813008976187564018) {
   out_5813008976187564018[0] = 1.0;
   out_5813008976187564018[1] = 0;
   out_5813008976187564018[2] = 0;
   out_5813008976187564018[3] = 0;
   out_5813008976187564018[4] = 0;
   out_5813008976187564018[5] = 0;
   out_5813008976187564018[6] = 0;
   out_5813008976187564018[7] = 0;
   out_5813008976187564018[8] = 0;
   out_5813008976187564018[9] = 0;
   out_5813008976187564018[10] = 1.0;
   out_5813008976187564018[11] = 0;
   out_5813008976187564018[12] = 0;
   out_5813008976187564018[13] = 0;
   out_5813008976187564018[14] = 0;
   out_5813008976187564018[15] = 0;
   out_5813008976187564018[16] = 0;
   out_5813008976187564018[17] = 0;
   out_5813008976187564018[18] = 0;
   out_5813008976187564018[19] = 0;
   out_5813008976187564018[20] = 1.0;
   out_5813008976187564018[21] = 0;
   out_5813008976187564018[22] = 0;
   out_5813008976187564018[23] = 0;
   out_5813008976187564018[24] = 0;
   out_5813008976187564018[25] = 0;
   out_5813008976187564018[26] = 0;
   out_5813008976187564018[27] = 0;
   out_5813008976187564018[28] = 0;
   out_5813008976187564018[29] = 0;
   out_5813008976187564018[30] = 1.0;
   out_5813008976187564018[31] = 0;
   out_5813008976187564018[32] = 0;
   out_5813008976187564018[33] = 0;
   out_5813008976187564018[34] = 0;
   out_5813008976187564018[35] = 0;
   out_5813008976187564018[36] = 0;
   out_5813008976187564018[37] = 0;
   out_5813008976187564018[38] = 0;
   out_5813008976187564018[39] = 0;
   out_5813008976187564018[40] = 1.0;
   out_5813008976187564018[41] = 0;
   out_5813008976187564018[42] = 0;
   out_5813008976187564018[43] = 0;
   out_5813008976187564018[44] = 0;
   out_5813008976187564018[45] = 0;
   out_5813008976187564018[46] = 0;
   out_5813008976187564018[47] = 0;
   out_5813008976187564018[48] = 0;
   out_5813008976187564018[49] = 0;
   out_5813008976187564018[50] = 1.0;
   out_5813008976187564018[51] = 0;
   out_5813008976187564018[52] = 0;
   out_5813008976187564018[53] = 0;
   out_5813008976187564018[54] = 0;
   out_5813008976187564018[55] = 0;
   out_5813008976187564018[56] = 0;
   out_5813008976187564018[57] = 0;
   out_5813008976187564018[58] = 0;
   out_5813008976187564018[59] = 0;
   out_5813008976187564018[60] = 1.0;
   out_5813008976187564018[61] = 0;
   out_5813008976187564018[62] = 0;
   out_5813008976187564018[63] = 0;
   out_5813008976187564018[64] = 0;
   out_5813008976187564018[65] = 0;
   out_5813008976187564018[66] = 0;
   out_5813008976187564018[67] = 0;
   out_5813008976187564018[68] = 0;
   out_5813008976187564018[69] = 0;
   out_5813008976187564018[70] = 1.0;
   out_5813008976187564018[71] = 0;
   out_5813008976187564018[72] = 0;
   out_5813008976187564018[73] = 0;
   out_5813008976187564018[74] = 0;
   out_5813008976187564018[75] = 0;
   out_5813008976187564018[76] = 0;
   out_5813008976187564018[77] = 0;
   out_5813008976187564018[78] = 0;
   out_5813008976187564018[79] = 0;
   out_5813008976187564018[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_987067726405563018) {
   out_987067726405563018[0] = state[0];
   out_987067726405563018[1] = state[1];
   out_987067726405563018[2] = state[2];
   out_987067726405563018[3] = state[3];
   out_987067726405563018[4] = state[4];
   out_987067726405563018[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8000000000000007*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_987067726405563018[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_987067726405563018[7] = state[7];
   out_987067726405563018[8] = state[8];
}
void F_fun(double *state, double dt, double *out_1828973490765447182) {
   out_1828973490765447182[0] = 1;
   out_1828973490765447182[1] = 0;
   out_1828973490765447182[2] = 0;
   out_1828973490765447182[3] = 0;
   out_1828973490765447182[4] = 0;
   out_1828973490765447182[5] = 0;
   out_1828973490765447182[6] = 0;
   out_1828973490765447182[7] = 0;
   out_1828973490765447182[8] = 0;
   out_1828973490765447182[9] = 0;
   out_1828973490765447182[10] = 1;
   out_1828973490765447182[11] = 0;
   out_1828973490765447182[12] = 0;
   out_1828973490765447182[13] = 0;
   out_1828973490765447182[14] = 0;
   out_1828973490765447182[15] = 0;
   out_1828973490765447182[16] = 0;
   out_1828973490765447182[17] = 0;
   out_1828973490765447182[18] = 0;
   out_1828973490765447182[19] = 0;
   out_1828973490765447182[20] = 1;
   out_1828973490765447182[21] = 0;
   out_1828973490765447182[22] = 0;
   out_1828973490765447182[23] = 0;
   out_1828973490765447182[24] = 0;
   out_1828973490765447182[25] = 0;
   out_1828973490765447182[26] = 0;
   out_1828973490765447182[27] = 0;
   out_1828973490765447182[28] = 0;
   out_1828973490765447182[29] = 0;
   out_1828973490765447182[30] = 1;
   out_1828973490765447182[31] = 0;
   out_1828973490765447182[32] = 0;
   out_1828973490765447182[33] = 0;
   out_1828973490765447182[34] = 0;
   out_1828973490765447182[35] = 0;
   out_1828973490765447182[36] = 0;
   out_1828973490765447182[37] = 0;
   out_1828973490765447182[38] = 0;
   out_1828973490765447182[39] = 0;
   out_1828973490765447182[40] = 1;
   out_1828973490765447182[41] = 0;
   out_1828973490765447182[42] = 0;
   out_1828973490765447182[43] = 0;
   out_1828973490765447182[44] = 0;
   out_1828973490765447182[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_1828973490765447182[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_1828973490765447182[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_1828973490765447182[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_1828973490765447182[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_1828973490765447182[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_1828973490765447182[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_1828973490765447182[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_1828973490765447182[53] = -9.8000000000000007*dt;
   out_1828973490765447182[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_1828973490765447182[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_1828973490765447182[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1828973490765447182[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1828973490765447182[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_1828973490765447182[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_1828973490765447182[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_1828973490765447182[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_1828973490765447182[62] = 0;
   out_1828973490765447182[63] = 0;
   out_1828973490765447182[64] = 0;
   out_1828973490765447182[65] = 0;
   out_1828973490765447182[66] = 0;
   out_1828973490765447182[67] = 0;
   out_1828973490765447182[68] = 0;
   out_1828973490765447182[69] = 0;
   out_1828973490765447182[70] = 1;
   out_1828973490765447182[71] = 0;
   out_1828973490765447182[72] = 0;
   out_1828973490765447182[73] = 0;
   out_1828973490765447182[74] = 0;
   out_1828973490765447182[75] = 0;
   out_1828973490765447182[76] = 0;
   out_1828973490765447182[77] = 0;
   out_1828973490765447182[78] = 0;
   out_1828973490765447182[79] = 0;
   out_1828973490765447182[80] = 1;
}
void h_25(double *state, double *unused, double *out_3296086676840854985) {
   out_3296086676840854985[0] = state[6];
}
void H_25(double *state, double *unused, double *out_4774617833311172584) {
   out_4774617833311172584[0] = 0;
   out_4774617833311172584[1] = 0;
   out_4774617833311172584[2] = 0;
   out_4774617833311172584[3] = 0;
   out_4774617833311172584[4] = 0;
   out_4774617833311172584[5] = 0;
   out_4774617833311172584[6] = 1;
   out_4774617833311172584[7] = 0;
   out_4774617833311172584[8] = 0;
}
void h_24(double *state, double *unused, double *out_5444175228385577307) {
   out_5444175228385577307[0] = state[4];
   out_5444175228385577307[1] = state[5];
}
void H_24(double *state, double *unused, double *out_5386631820324253920) {
   out_5386631820324253920[0] = 0;
   out_5386631820324253920[1] = 0;
   out_5386631820324253920[2] = 0;
   out_5386631820324253920[3] = 0;
   out_5386631820324253920[4] = 1;
   out_5386631820324253920[5] = 0;
   out_5386631820324253920[6] = 0;
   out_5386631820324253920[7] = 0;
   out_5386631820324253920[8] = 0;
   out_5386631820324253920[9] = 0;
   out_5386631820324253920[10] = 0;
   out_5386631820324253920[11] = 0;
   out_5386631820324253920[12] = 0;
   out_5386631820324253920[13] = 0;
   out_5386631820324253920[14] = 1;
   out_5386631820324253920[15] = 0;
   out_5386631820324253920[16] = 0;
   out_5386631820324253920[17] = 0;
}
void h_30(double *state, double *unused, double *out_3890866227617203344) {
   out_3890866227617203344[0] = state[4];
}
void H_30(double *state, double *unused, double *out_2256284874803923957) {
   out_2256284874803923957[0] = 0;
   out_2256284874803923957[1] = 0;
   out_2256284874803923957[2] = 0;
   out_2256284874803923957[3] = 0;
   out_2256284874803923957[4] = 1;
   out_2256284874803923957[5] = 0;
   out_2256284874803923957[6] = 0;
   out_2256284874803923957[7] = 0;
   out_2256284874803923957[8] = 0;
}
void h_26(double *state, double *unused, double *out_2508175289796645802) {
   out_2508175289796645802[0] = state[7];
}
void H_26(double *state, double *unused, double *out_8516121152185228808) {
   out_8516121152185228808[0] = 0;
   out_8516121152185228808[1] = 0;
   out_8516121152185228808[2] = 0;
   out_8516121152185228808[3] = 0;
   out_8516121152185228808[4] = 0;
   out_8516121152185228808[5] = 0;
   out_8516121152185228808[6] = 0;
   out_8516121152185228808[7] = 1;
   out_8516121152185228808[8] = 0;
}
void h_27(double *state, double *unused, double *out_5109570142803371668) {
   out_5109570142803371668[0] = state[3];
}
void H_27(double *state, double *unused, double *out_4431048186604348868) {
   out_4431048186604348868[0] = 0;
   out_4431048186604348868[1] = 0;
   out_4431048186604348868[2] = 0;
   out_4431048186604348868[3] = 1;
   out_4431048186604348868[4] = 0;
   out_4431048186604348868[5] = 0;
   out_4431048186604348868[6] = 0;
   out_4431048186604348868[7] = 0;
   out_4431048186604348868[8] = 0;
}
void h_29(double *state, double *unused, double *out_4834376080518865779) {
   out_4834376080518865779[0] = state[1];
}
void H_29(double *state, double *unused, double *out_1746053530489531773) {
   out_1746053530489531773[0] = 0;
   out_1746053530489531773[1] = 1;
   out_1746053530489531773[2] = 0;
   out_1746053530489531773[3] = 0;
   out_1746053530489531773[4] = 0;
   out_1746053530489531773[5] = 0;
   out_1746053530489531773[6] = 0;
   out_1746053530489531773[7] = 0;
   out_1746053530489531773[8] = 0;
}
void h_28(double *state, double *unused, double *out_107896875142526023) {
   out_107896875142526023[0] = state[0];
}
void H_28(double *state, double *unused, double *out_6828452547559062347) {
   out_6828452547559062347[0] = 1;
   out_6828452547559062347[1] = 0;
   out_6828452547559062347[2] = 0;
   out_6828452547559062347[3] = 0;
   out_6828452547559062347[4] = 0;
   out_6828452547559062347[5] = 0;
   out_6828452547559062347[6] = 0;
   out_6828452547559062347[7] = 0;
   out_6828452547559062347[8] = 0;
}
void h_31(double *state, double *unused, double *out_8660612017835334146) {
   out_8660612017835334146[0] = state[8];
}
void H_31(double *state, double *unused, double *out_9142329254418580284) {
   out_9142329254418580284[0] = 0;
   out_9142329254418580284[1] = 0;
   out_9142329254418580284[2] = 0;
   out_9142329254418580284[3] = 0;
   out_9142329254418580284[4] = 0;
   out_9142329254418580284[5] = 0;
   out_9142329254418580284[6] = 0;
   out_9142329254418580284[7] = 0;
   out_9142329254418580284[8] = 1;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_25, H_25, NULL, in_z, in_R, in_ea, MAHA_THRESH_25);
}
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<2, 3, 0>(in_x, in_P, h_24, H_24, NULL, in_z, in_R, in_ea, MAHA_THRESH_24);
}
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_30, H_30, NULL, in_z, in_R, in_ea, MAHA_THRESH_30);
}
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_26, H_26, NULL, in_z, in_R, in_ea, MAHA_THRESH_26);
}
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_27, H_27, NULL, in_z, in_R, in_ea, MAHA_THRESH_27);
}
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_29, H_29, NULL, in_z, in_R, in_ea, MAHA_THRESH_29);
}
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_28, H_28, NULL, in_z, in_R, in_ea, MAHA_THRESH_28);
}
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<1, 3, 0>(in_x, in_P, h_31, H_31, NULL, in_z, in_R, in_ea, MAHA_THRESH_31);
}
void car_err_fun(double *nom_x, double *delta_x, double *out_1086654683844306915) {
  err_fun(nom_x, delta_x, out_1086654683844306915);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_1205985898548646392) {
  inv_err_fun(nom_x, true_x, out_1205985898548646392);
}
void car_H_mod_fun(double *state, double *out_5813008976187564018) {
  H_mod_fun(state, out_5813008976187564018);
}
void car_f_fun(double *state, double dt, double *out_987067726405563018) {
  f_fun(state,  dt, out_987067726405563018);
}
void car_F_fun(double *state, double dt, double *out_1828973490765447182) {
  F_fun(state,  dt, out_1828973490765447182);
}
void car_h_25(double *state, double *unused, double *out_3296086676840854985) {
  h_25(state, unused, out_3296086676840854985);
}
void car_H_25(double *state, double *unused, double *out_4774617833311172584) {
  H_25(state, unused, out_4774617833311172584);
}
void car_h_24(double *state, double *unused, double *out_5444175228385577307) {
  h_24(state, unused, out_5444175228385577307);
}
void car_H_24(double *state, double *unused, double *out_5386631820324253920) {
  H_24(state, unused, out_5386631820324253920);
}
void car_h_30(double *state, double *unused, double *out_3890866227617203344) {
  h_30(state, unused, out_3890866227617203344);
}
void car_H_30(double *state, double *unused, double *out_2256284874803923957) {
  H_30(state, unused, out_2256284874803923957);
}
void car_h_26(double *state, double *unused, double *out_2508175289796645802) {
  h_26(state, unused, out_2508175289796645802);
}
void car_H_26(double *state, double *unused, double *out_8516121152185228808) {
  H_26(state, unused, out_8516121152185228808);
}
void car_h_27(double *state, double *unused, double *out_5109570142803371668) {
  h_27(state, unused, out_5109570142803371668);
}
void car_H_27(double *state, double *unused, double *out_4431048186604348868) {
  H_27(state, unused, out_4431048186604348868);
}
void car_h_29(double *state, double *unused, double *out_4834376080518865779) {
  h_29(state, unused, out_4834376080518865779);
}
void car_H_29(double *state, double *unused, double *out_1746053530489531773) {
  H_29(state, unused, out_1746053530489531773);
}
void car_h_28(double *state, double *unused, double *out_107896875142526023) {
  h_28(state, unused, out_107896875142526023);
}
void car_H_28(double *state, double *unused, double *out_6828452547559062347) {
  H_28(state, unused, out_6828452547559062347);
}
void car_h_31(double *state, double *unused, double *out_8660612017835334146) {
  h_31(state, unused, out_8660612017835334146);
}
void car_H_31(double *state, double *unused, double *out_9142329254418580284) {
  H_31(state, unused, out_9142329254418580284);
}
void car_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
void car_set_mass(double x) {
  set_mass(x);
}
void car_set_rotational_inertia(double x) {
  set_rotational_inertia(x);
}
void car_set_center_to_front(double x) {
  set_center_to_front(x);
}
void car_set_center_to_rear(double x) {
  set_center_to_rear(x);
}
void car_set_stiffness_front(double x) {
  set_stiffness_front(x);
}
void car_set_stiffness_rear(double x) {
  set_stiffness_rear(x);
}
}

const EKF car = {
  .name = "car",
  .kinds = { 25, 24, 30, 26, 27, 29, 28, 31 },
  .feature_kinds = {  },
  .f_fun = car_f_fun,
  .F_fun = car_F_fun,
  .err_fun = car_err_fun,
  .inv_err_fun = car_inv_err_fun,
  .H_mod_fun = car_H_mod_fun,
  .predict = car_predict,
  .hs = {
    { 25, car_h_25 },
    { 24, car_h_24 },
    { 30, car_h_30 },
    { 26, car_h_26 },
    { 27, car_h_27 },
    { 29, car_h_29 },
    { 28, car_h_28 },
    { 31, car_h_31 },
  },
  .Hs = {
    { 25, car_H_25 },
    { 24, car_H_24 },
    { 30, car_H_30 },
    { 26, car_H_26 },
    { 27, car_H_27 },
    { 29, car_H_29 },
    { 28, car_H_28 },
    { 31, car_H_31 },
  },
  .updates = {
    { 25, car_update_25 },
    { 24, car_update_24 },
    { 30, car_update_30 },
    { 26, car_update_26 },
    { 27, car_update_27 },
    { 29, car_update_29 },
    { 28, car_update_28 },
    { 31, car_update_31 },
  },
  .Hes = {
  },
  .sets = {
    { "mass", car_set_mass },
    { "rotational_inertia", car_set_rotational_inertia },
    { "center_to_front", car_set_center_to_front },
    { "center_to_rear", car_set_center_to_rear },
    { "stiffness_front", car_set_stiffness_front },
    { "stiffness_rear", car_set_stiffness_rear },
  },
  .extra_routines = {
  },
};

ekf_lib_init(car)
