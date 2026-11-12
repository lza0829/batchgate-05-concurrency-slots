import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.vue'
import Jobs from './pages/Jobs.vue'
import Orchestrate from './pages/Orchestrate.vue'
import Attempts from './pages/Attempts.vue'
import Watermarks from './pages/Watermarks.vue'
import Settings from './pages/Settings.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/jobs', component: Jobs },
    { path: '/orchestrate', component: Orchestrate },
    { path: '/attempts', component: Attempts },
    { path: '/watermarks', component: Watermarks },
    { path: '/settings', component: Settings },
  ],
})
