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
void err_fun(double *nom_x, double *delta_x, double *out_5524144404166832695) {
   out_5524144404166832695[0] = delta_x[0] + nom_x[0];
   out_5524144404166832695[1] = delta_x[1] + nom_x[1];
   out_5524144404166832695[2] = delta_x[2] + nom_x[2];
   out_5524144404166832695[3] = delta_x[3] + nom_x[3];
   out_5524144404166832695[4] = delta_x[4] + nom_x[4];
   out_5524144404166832695[5] = delta_x[5] + nom_x[5];
   out_5524144404166832695[6] = delta_x[6] + nom_x[6];
   out_5524144404166832695[7] = delta_x[7] + nom_x[7];
   out_5524144404166832695[8] = delta_x[8] + nom_x[8];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_2907022573236161302) {
   out_2907022573236161302[0] = -nom_x[0] + true_x[0];
   out_2907022573236161302[1] = -nom_x[1] + true_x[1];
   out_2907022573236161302[2] = -nom_x[2] + true_x[2];
   out_2907022573236161302[3] = -nom_x[3] + true_x[3];
   out_2907022573236161302[4] = -nom_x[4] + true_x[4];
   out_2907022573236161302[5] = -nom_x[5] + true_x[5];
   out_2907022573236161302[6] = -nom_x[6] + true_x[6];
   out_2907022573236161302[7] = -nom_x[7] + true_x[7];
   out_2907022573236161302[8] = -nom_x[8] + true_x[8];
}
void H_mod_fun(double *state, double *out_6800657185839521855) {
   out_6800657185839521855[0] = 1.0;
   out_6800657185839521855[1] = 0;
   out_6800657185839521855[2] = 0;
   out_6800657185839521855[3] = 0;
   out_6800657185839521855[4] = 0;
   out_6800657185839521855[5] = 0;
   out_6800657185839521855[6] = 0;
   out_6800657185839521855[7] = 0;
   out_6800657185839521855[8] = 0;
   out_6800657185839521855[9] = 0;
   out_6800657185839521855[10] = 1.0;
   out_6800657185839521855[11] = 0;
   out_6800657185839521855[12] = 0;
   out_6800657185839521855[13] = 0;
   out_6800657185839521855[14] = 0;
   out_6800657185839521855[15] = 0;
   out_6800657185839521855[16] = 0;
   out_6800657185839521855[17] = 0;
   out_6800657185839521855[18] = 0;
   out_6800657185839521855[19] = 0;
   out_6800657185839521855[20] = 1.0;
   out_6800657185839521855[21] = 0;
   out_6800657185839521855[22] = 0;
   out_6800657185839521855[23] = 0;
   out_6800657185839521855[24] = 0;
   out_6800657185839521855[25] = 0;
   out_6800657185839521855[26] = 0;
   out_6800657185839521855[27] = 0;
   out_6800657185839521855[28] = 0;
   out_6800657185839521855[29] = 0;
   out_6800657185839521855[30] = 1.0;
   out_6800657185839521855[31] = 0;
   out_6800657185839521855[32] = 0;
   out_6800657185839521855[33] = 0;
   out_6800657185839521855[34] = 0;
   out_6800657185839521855[35] = 0;
   out_6800657185839521855[36] = 0;
   out_6800657185839521855[37] = 0;
   out_6800657185839521855[38] = 0;
   out_6800657185839521855[39] = 0;
   out_6800657185839521855[40] = 1.0;
   out_6800657185839521855[41] = 0;
   out_6800657185839521855[42] = 0;
   out_6800657185839521855[43] = 0;
   out_6800657185839521855[44] = 0;
   out_6800657185839521855[45] = 0;
   out_6800657185839521855[46] = 0;
   out_6800657185839521855[47] = 0;
   out_6800657185839521855[48] = 0;
   out_6800657185839521855[49] = 0;
   out_6800657185839521855[50] = 1.0;
   out_6800657185839521855[51] = 0;
   out_6800657185839521855[52] = 0;
   out_6800657185839521855[53] = 0;
   out_6800657185839521855[54] = 0;
   out_6800657185839521855[55] = 0;
   out_6800657185839521855[56] = 0;
   out_6800657185839521855[57] = 0;
   out_6800657185839521855[58] = 0;
   out_6800657185839521855[59] = 0;
   out_6800657185839521855[60] = 1.0;
   out_6800657185839521855[61] = 0;
   out_6800657185839521855[62] = 0;
   out_6800657185839521855[63] = 0;
   out_6800657185839521855[64] = 0;
   out_6800657185839521855[65] = 0;
   out_6800657185839521855[66] = 0;
   out_6800657185839521855[67] = 0;
   out_6800657185839521855[68] = 0;
   out_6800657185839521855[69] = 0;
   out_6800657185839521855[70] = 1.0;
   out_6800657185839521855[71] = 0;
   out_6800657185839521855[72] = 0;
   out_6800657185839521855[73] = 0;
   out_6800657185839521855[74] = 0;
   out_6800657185839521855[75] = 0;
   out_6800657185839521855[76] = 0;
   out_6800657185839521855[77] = 0;
   out_6800657185839521855[78] = 0;
   out_6800657185839521855[79] = 0;
   out_6800657185839521855[80] = 1.0;
}
void f_fun(double *state, double dt, double *out_711305531206779806) {
   out_711305531206779806[0] = state[0];
   out_711305531206779806[1] = state[1];
   out_711305531206779806[2] = state[2];
   out_711305531206779806[3] = state[3];
   out_711305531206779806[4] = state[4];
   out_711305531206779806[5] = dt*((-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]))*state[6] - 9.8000000000000007*state[8] + stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*state[1]) + (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*state[4])) + state[5];
   out_711305531206779806[6] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*state[4])) + state[6];
   out_711305531206779806[7] = state[7];
   out_711305531206779806[8] = state[8];
}
void F_fun(double *state, double dt, double *out_8093286998772872447) {
   out_8093286998772872447[0] = 1;
   out_8093286998772872447[1] = 0;
   out_8093286998772872447[2] = 0;
   out_8093286998772872447[3] = 0;
   out_8093286998772872447[4] = 0;
   out_8093286998772872447[5] = 0;
   out_8093286998772872447[6] = 0;
   out_8093286998772872447[7] = 0;
   out_8093286998772872447[8] = 0;
   out_8093286998772872447[9] = 0;
   out_8093286998772872447[10] = 1;
   out_8093286998772872447[11] = 0;
   out_8093286998772872447[12] = 0;
   out_8093286998772872447[13] = 0;
   out_8093286998772872447[14] = 0;
   out_8093286998772872447[15] = 0;
   out_8093286998772872447[16] = 0;
   out_8093286998772872447[17] = 0;
   out_8093286998772872447[18] = 0;
   out_8093286998772872447[19] = 0;
   out_8093286998772872447[20] = 1;
   out_8093286998772872447[21] = 0;
   out_8093286998772872447[22] = 0;
   out_8093286998772872447[23] = 0;
   out_8093286998772872447[24] = 0;
   out_8093286998772872447[25] = 0;
   out_8093286998772872447[26] = 0;
   out_8093286998772872447[27] = 0;
   out_8093286998772872447[28] = 0;
   out_8093286998772872447[29] = 0;
   out_8093286998772872447[30] = 1;
   out_8093286998772872447[31] = 0;
   out_8093286998772872447[32] = 0;
   out_8093286998772872447[33] = 0;
   out_8093286998772872447[34] = 0;
   out_8093286998772872447[35] = 0;
   out_8093286998772872447[36] = 0;
   out_8093286998772872447[37] = 0;
   out_8093286998772872447[38] = 0;
   out_8093286998772872447[39] = 0;
   out_8093286998772872447[40] = 1;
   out_8093286998772872447[41] = 0;
   out_8093286998772872447[42] = 0;
   out_8093286998772872447[43] = 0;
   out_8093286998772872447[44] = 0;
   out_8093286998772872447[45] = dt*(stiffness_front*(-state[2] - state[3] + state[7])/(mass*state[1]) + (-stiffness_front - stiffness_rear)*state[5]/(mass*state[4]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[6]/(mass*state[4]));
   out_8093286998772872447[46] = -dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(mass*pow(state[1], 2));
   out_8093286998772872447[47] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_8093286998772872447[48] = -dt*stiffness_front*state[0]/(mass*state[1]);
   out_8093286998772872447[49] = dt*((-1 - (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*pow(state[4], 2)))*state[6] - (-stiffness_front*state[0] - stiffness_rear*state[0])*state[5]/(mass*pow(state[4], 2)));
   out_8093286998772872447[50] = dt*(-stiffness_front*state[0] - stiffness_rear*state[0])/(mass*state[4]) + 1;
   out_8093286998772872447[51] = dt*(-state[4] + (-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(mass*state[4]));
   out_8093286998772872447[52] = dt*stiffness_front*state[0]/(mass*state[1]);
   out_8093286998772872447[53] = -9.8000000000000007*dt;
   out_8093286998772872447[54] = dt*(center_to_front*stiffness_front*(-state[2] - state[3] + state[7])/(rotational_inertia*state[1]) + (-center_to_front*stiffness_front + center_to_rear*stiffness_rear)*state[5]/(rotational_inertia*state[4]) + (-pow(center_to_front, 2)*stiffness_front - pow(center_to_rear, 2)*stiffness_rear)*state[6]/(rotational_inertia*state[4]));
   out_8093286998772872447[55] = -center_to_front*dt*stiffness_front*(-state[2] - state[3] + state[7])*state[0]/(rotational_inertia*pow(state[1], 2));
   out_8093286998772872447[56] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8093286998772872447[57] = -center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8093286998772872447[58] = dt*(-(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])*state[5]/(rotational_inertia*pow(state[4], 2)) - (-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])*state[6]/(rotational_inertia*pow(state[4], 2)));
   out_8093286998772872447[59] = dt*(-center_to_front*stiffness_front*state[0] + center_to_rear*stiffness_rear*state[0])/(rotational_inertia*state[4]);
   out_8093286998772872447[60] = dt*(-pow(center_to_front, 2)*stiffness_front*state[0] - pow(center_to_rear, 2)*stiffness_rear*state[0])/(rotational_inertia*state[4]) + 1;
   out_8093286998772872447[61] = center_to_front*dt*stiffness_front*state[0]/(rotational_inertia*state[1]);
   out_8093286998772872447[62] = 0;
   out_8093286998772872447[63] = 0;
   out_8093286998772872447[64] = 0;
   out_8093286998772872447[65] = 0;
   out_8093286998772872447[66] = 0;
   out_8093286998772872447[67] = 0;
   out_8093286998772872447[68] = 0;
   out_8093286998772872447[69] = 0;
   out_8093286998772872447[70] = 1;
   out_8093286998772872447[71] = 0;
   out_8093286998772872447[72] = 0;
   out_8093286998772872447[73] = 0;
   out_8093286998772872447[74] = 0;
   out_8093286998772872447[75] = 0;
   out_8093286998772872447[76] = 0;
   out_8093286998772872447[77] = 0;
   out_8093286998772872447[78] = 0;
   out_8093286998772872447[79] = 0;
   out_8093286998772872447[80] = 1;
}
void h_25(double *state, double *unused, double *out_8779555538269851311) {
   out_8779555538269851311[0] = state[6];
}
void H_25(double *state, double *unused, double *out_2822056187165656386) {
   out_2822056187165656386[0] = 0;
   out_2822056187165656386[1] = 0;
   out_2822056187165656386[2] = 0;
   out_2822056187165656386[3] = 0;
   out_2822056187165656386[4] = 0;
   out_2822056187165656386[5] = 0;
   out_2822056187165656386[6] = 1;
   out_2822056187165656386[7] = 0;
   out_2822056187165656386[8] = 0;
}
void h_24(double *state, double *unused, double *out_8584418487322312095) {
   out_8584418487322312095[0] = state[4];
   out_8584418487322312095[1] = state[5];
}
void H_24(double *state, double *unused, double *out_9023088867016817812) {
   out_9023088867016817812[0] = 0;
   out_9023088867016817812[1] = 0;
   out_9023088867016817812[2] = 0;
   out_9023088867016817812[3] = 0;
   out_9023088867016817812[4] = 1;
   out_9023088867016817812[5] = 0;
   out_9023088867016817812[6] = 0;
   out_9023088867016817812[7] = 0;
   out_9023088867016817812[8] = 0;
   out_9023088867016817812[9] = 0;
   out_9023088867016817812[10] = 0;
   out_9023088867016817812[11] = 0;
   out_9023088867016817812[12] = 0;
   out_9023088867016817812[13] = 0;
   out_9023088867016817812[14] = 1;
   out_9023088867016817812[15] = 0;
   out_9023088867016817812[16] = 0;
   out_9023088867016817812[17] = 0;
}
void h_30(double *state, double *unused, double *out_2559178355422837342) {
   out_2559178355422837342[0] = state[4];
}
void H_30(double *state, double *unused, double *out_4094634154325960369) {
   out_4094634154325960369[0] = 0;
   out_4094634154325960369[1] = 0;
   out_4094634154325960369[2] = 0;
   out_4094634154325960369[3] = 0;
   out_4094634154325960369[4] = 1;
   out_4094634154325960369[5] = 0;
   out_4094634154325960369[6] = 0;
   out_4094634154325960369[7] = 0;
   out_4094634154325960369[8] = 0;
}
void h_26(double *state, double *unused, double *out_7560851623083682987) {
   out_7560851623083682987[0] = state[7];
}
void H_26(double *state, double *unused, double *out_6563559506039712610) {
   out_6563559506039712610[0] = 0;
   out_6563559506039712610[1] = 0;
   out_6563559506039712610[2] = 0;
   out_6563559506039712610[3] = 0;
   out_6563559506039712610[4] = 0;
   out_6563559506039712610[5] = 0;
   out_6563559506039712610[6] = 0;
   out_6563559506039712610[7] = 1;
   out_6563559506039712610[8] = 0;
}
void h_27(double *state, double *unused, double *out_3268147018025851159) {
   out_3268147018025851159[0] = state[3];
}
void H_27(double *state, double *unused, double *out_5126158446109321367) {
   out_5126158446109321367[0] = 0;
   out_5126158446109321367[1] = 0;
   out_5126158446109321367[2] = 0;
   out_5126158446109321367[3] = 1;
   out_5126158446109321367[4] = 0;
   out_5126158446109321367[5] = 0;
   out_5126158446109321367[6] = 0;
   out_5126158446109321367[7] = 0;
   out_5126158446109321367[8] = 0;
}
void h_29(double *state, double *unused, double *out_6905596546279873509) {
   out_6905596546279873509[0] = state[1];
}
void H_29(double *state, double *unused, double *out_2441163789994504272) {
   out_2441163789994504272[0] = 0;
   out_2441163789994504272[1] = 1;
   out_2441163789994504272[2] = 0;
   out_2441163789994504272[3] = 0;
   out_2441163789994504272[4] = 0;
   out_2441163789994504272[5] = 0;
   out_2441163789994504272[6] = 0;
   out_2441163789994504272[7] = 0;
   out_2441163789994504272[8] = 0;
}
void h_28(double *state, double *unused, double *out_3871462902702328676) {
   out_3871462902702328676[0] = state[0];
}
void H_28(double *state, double *unused, double *out_477533518429178021) {
   out_477533518429178021[0] = 1;
   out_477533518429178021[1] = 0;
   out_477533518429178021[2] = 0;
   out_477533518429178021[3] = 0;
   out_477533518429178021[4] = 0;
   out_477533518429178021[5] = 0;
   out_477533518429178021[6] = 0;
   out_477533518429178021[7] = 0;
   out_477533518429178021[8] = 0;
}
void h_31(double *state, double *unused, double *out_4681252239990479447) {
   out_4681252239990479447[0] = state[8];
}
void H_31(double *state, double *unused, double *out_2791410225288695958) {
   out_2791410225288695958[0] = 0;
   out_2791410225288695958[1] = 0;
   out_2791410225288695958[2] = 0;
   out_2791410225288695958[3] = 0;
   out_2791410225288695958[4] = 0;
   out_2791410225288695958[5] = 0;
   out_2791410225288695958[6] = 0;
   out_2791410225288695958[7] = 0;
   out_2791410225288695958[8] = 1;
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
void car_err_fun(double *nom_x, double *delta_x, double *out_5524144404166832695) {
  err_fun(nom_x, delta_x, out_5524144404166832695);
}
void car_inv_err_fun(double *nom_x, double *true_x, double *out_2907022573236161302) {
  inv_err_fun(nom_x, true_x, out_2907022573236161302);
}
void car_H_mod_fun(double *state, double *out_6800657185839521855) {
  H_mod_fun(state, out_6800657185839521855);
}
void car_f_fun(double *state, double dt, double *out_711305531206779806) {
  f_fun(state,  dt, out_711305531206779806);
}
void car_F_fun(double *state, double dt, double *out_8093286998772872447) {
  F_fun(state,  dt, out_8093286998772872447);
}
void car_h_25(double *state, double *unused, double *out_8779555538269851311) {
  h_25(state, unused, out_8779555538269851311);
}
void car_H_25(double *state, double *unused, double *out_2822056187165656386) {
  H_25(state, unused, out_2822056187165656386);
}
void car_h_24(double *state, double *unused, double *out_8584418487322312095) {
  h_24(state, unused, out_8584418487322312095);
}
void car_H_24(double *state, double *unused, double *out_9023088867016817812) {
  H_24(state, unused, out_9023088867016817812);
}
void car_h_30(double *state, double *unused, double *out_2559178355422837342) {
  h_30(state, unused, out_2559178355422837342);
}
void car_H_30(double *state, double *unused, double *out_4094634154325960369) {
  H_30(state, unused, out_4094634154325960369);
}
void car_h_26(double *state, double *unused, double *out_7560851623083682987) {
  h_26(state, unused, out_7560851623083682987);
}
void car_H_26(double *state, double *unused, double *out_6563559506039712610) {
  H_26(state, unused, out_6563559506039712610);
}
void car_h_27(double *state, double *unused, double *out_3268147018025851159) {
  h_27(state, unused, out_3268147018025851159);
}
void car_H_27(double *state, double *unused, double *out_5126158446109321367) {
  H_27(state, unused, out_5126158446109321367);
}
void car_h_29(double *state, double *unused, double *out_6905596546279873509) {
  h_29(state, unused, out_6905596546279873509);
}
void car_H_29(double *state, double *unused, double *out_2441163789994504272) {
  H_29(state, unused, out_2441163789994504272);
}
void car_h_28(double *state, double *unused, double *out_3871462902702328676) {
  h_28(state, unused, out_3871462902702328676);
}
void car_H_28(double *state, double *unused, double *out_477533518429178021) {
  H_28(state, unused, out_477533518429178021);
}
void car_h_31(double *state, double *unused, double *out_4681252239990479447) {
  h_31(state, unused, out_4681252239990479447);
}
void car_H_31(double *state, double *unused, double *out_2791410225288695958) {
  H_31(state, unused, out_2791410225288695958);
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
