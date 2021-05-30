import Vue from "vue";
import App from "./App.vue";
import router from "./router";
import axios from "axios";

axios.defaults.headers.common['Access-Control-Allow-Origin'] = '*';

import { store } from "./store/store";
Vue.config.productionTip = false;

new Vue({
  router,
  store,
  axios,
  render: (h) => h(App),
}).$mount("#app");
