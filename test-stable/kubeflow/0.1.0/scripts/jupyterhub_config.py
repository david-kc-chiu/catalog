import json
import os
import string
import escapism
from kubespawner.spawner import KubeSpawner
from jhub_remote_user_authenticator.remote_user_auth import RemoteUserAuthenticator
from oauthenticator.github import GitHubOAuthenticator
from kubernetes import client, config
import re

SERVICE_ACCOUNT_SECRET_MOUNT = '/var/run/secrets/sa'

class KubeFormSpawner(KubeSpawner):
    nodes_capacity=[]
    pods_requests=[]
    nodes_available=[]
    flavor_lists=[]
    pods_list=None
    nodes_list=None
    APISERVER=""
    KUBE_TOKEN=""
    gpuAllocate=False
    def get_nodes_list(self):
        del self.nodes_capacity[:]
        config.load_incluster_config()
        v1=client.CoreV1Api()
        self.nodes_list = v1.list_node()

        for i in self.nodes_list.items:
            name = i.metadata.name
            taints = i.spec.taints

            _effect = ""
            if taints != None:
                for _taint in taints:
                    if _taint.effect == "NoSchedule" or _taint.effect == "NoExecute":
                        _effect = "NoSchedule"
            if taints == None or _effect != "NoSchedule":
                capacity_cpu = 0
                capacity_mem = 0
                capacity_gpu = 0
                capacity_storage = 0
                if 'cpu' in i.status.capacity:
                    capacity_cpu = int(i.status.capacity['cpu'])*1000
                if 'memory' in i.status.capacity:
                    capacity_mem = i.status.capacity['memory']
                    if 'Ki' in capacity_mem:
                        capacity_mem = int(int(capacity_mem[:-2]) / 1024 / 1024)
                    elif 'Mi' in capacity_mem:
                        capacity_mem = int(int(capacity_mem[:-2]) / 1024)
                    elif 'Gi' in capacity_mem:
                        capacity_mem = int(capacity_mem[:-2])
                    else:
                        capacity_mem = int(capacity_mem[:-2])
                if 'ephemeral-storage' in i.status.capacity:
                    capacity_storage = i.status.capacity['ephemeral-storage']
                    if 'Ki' in capacity_storage:
                        capacity_storage = int(int(capacity_storage[:-2]) / 1024 / 1024)
                    elif 'Mi' in capacity_storage:
                        capacity_storage = int(capacity_storage[:-2] / 1024)
                    elif 'Gi' in capacity_storage:
                        capacity_storage = int(capacity_storage[:-2])
                    else:
                        capacity_storage = int(capacity_storage[:-2])
                capacity_cpu = capacity_cpu - 1000 # system reserve
                capacity_mem = capacity_mem - 10 # system reserve 10Gi
                capacity_storage = capacity_storage - 20 # system reserve 20Gi

                if 'nvidia.com/gpu' in i.status.capacity:
                    capacity_gpu = int(i.status.capacity['nvidia.com/gpu'])

                self.nodes_capacity.append({"name":str(name), 
                                            "capacity_cpu":int(capacity_cpu), 
                                            "capacity_mem":int(capacity_mem),
                                            "capacity_storage":int(capacity_storage),
                                            "capacity_gpu":capacity_gpu})
              #self.log.info("node name : %20s, capacity cpu : %10s, memroy : %20s, gpu : %10s"%(name, capacity_cpu, capacity_mem, capacity_gpu))
    def get_pods_list(self):
        del self.pods_requests[:]
        config.load_incluster_config()
        v1=client.CoreV1Api()
        self.pods_list = v1.list_pod_for_all_namespaces(watch=False)

        for i in self.pods_list.items:
            name=i.metadata.name
            node_name=i.spec.node_name
            limits_cpu = limits_mem = limits_gpu = requests_cpu = requests_mem = requests_gpu = limits_storage = requests_storage = 0
            if i.spec.containers[0].resources.limits != None:
                if 'cpu' in i.spec.containers[0].resources.limits:
                    limits_cpu=i.spec.containers[0].resources.limits['cpu']
                if 'memory' in i.spec.containers[0].resources.limits:
                    limits_mem=i.spec.containers[0].resources.limits['memory']
                if 'ephemeral-storage' in i.spec.containers[0].resources.limits:
                    limits_storage = i.spec.containers[0].resources.limits['ephemeral-storage']
                if 'nvidia.com/gpu' in i.spec.containers[0].resources.limits:
                    limits_gpu=i.spec.containers[0].resources.limits['nvidia.com/gpu']

            if i.spec.containers[0].resources.requests != None:
                if 'cpu' in i.spec.containers[0].resources.requests:
                    requests_cpu=i.spec.containers[0].resources.requests['cpu']
                if 'memory' in i.spec.containers[0].resources.requests:
                    requests_mem=i.spec.containers[0].resources.requests['memory']
                if 'ephemeral-storage' in i.spec.containers[0].resources.requests:
                    requests_storage = i.spec.containers[0].resources.requests['ephemeral-storage']
                if 'nvidia.com/gpu' in i.spec.containers[0].resources.requests:
                    requests_gpu=i.spec.containers[0].resources.requests['nvidia.com/gpu']

            #if limits_cpu != 0 or requests_cpu != 0 or requests_gpu != 0:
            if limits_cpu != 0 or requests_cpu != 0 or limits_mem != 0 or requests_mem != 0 or requests_gpu != 0 or limits_gpu != 0 or limits_storage != 0 or requests_storage != 0:
                #self.log.info("name : %50s, limit CPU : %5s, limit Memory : %5s, Requests CPU : request_cpu : %5s, Request Memory : %5s, node name : %10s"%(name, limits_cpu, limits_mem, requests_cpu, requests_mem, node_name))
                self.pods_requests.append({"name":str(name),
                                           "limits_cpu":str(limits_cpu),
                                           "limits_mem":str(limits_mem),
                                           "limits_storage":str(limits_storage),
                                           "limits_gpu":str(limits_gpu),
                                           "requests_cpu":str(requests_cpu),
                                           "requests_mem":str(requests_mem),
                                           "requests_storage":str(requests_storage),
                                           "requests_gpu":str(requests_gpu),
                                           "node_name":str(node_name)})

    def get_nodes_available_resources(self):
        del self.nodes_available[:]
  
        self.get_nodes_list()
        self.get_pods_list()
        self.nodes_available = self.nodes_capacity.copy()
       
        self.log.info("---   Node Capacity  ---")
        self.log.info("{:<18} {:<8} {:<8} {:<8} {:<8}".format("NodeName", "CapCPU", "CapMem", "CapStg", "CapGPU"))
        for node in self.nodes_capacity:
            self.log.info("{:<18} {:<8} {:<8} {:<8} {:<8}".format(node["name"], node["capacity_cpu"], node["capacity_mem"], node["capacity_storage"], node["capacity_gpu"]))
        self.log.info("---  POD request resources  --")
        self.log.info("{:<18} {:<40} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8}".format("NodeName", "POD-Name", "ReqCPU", "ReqMem", "ReqStg", "ReqGPU", "LimCPU", "LimMem", "LimStg", "LimGPU")) 
        for pod in self.pods_requests:
            self.log.info("{:<18} {:<40} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8} {:<8}".format(pod["node_name"], pod["name"], pod["requests_cpu"],pod["requests_mem"], pod["requests_storage"], pod["requests_gpu"], 
                                                                                                                                pod["limits_cpu"], pod["limits_mem"], pod["limits_storage"],pod["limits_gpu"]))

        for pod in self.pods_requests:
            for node in self.nodes_available:
                if pod["node_name"] == node["name"]:
                    '''CPU'''
                    req_cpu=0
                    if 'm' in pod["requests_cpu"]:
                        req_cpu = int(pod["requests_cpu"][:-1])
                    elif str(pod["requests_cpu"]) == '0':
                        req_cpu = 0
                    else :
                        req_cpu = int(pod["requests_cpu"])*1000
                    node["capacity_cpu"] = node["capacity_cpu"] - req_cpu
  
                    '''Memory'''
                    m = re.split('(\d+)',pod["requests_mem"])
                    req_mem = int(m[1])
                    if 'Ki' in pod["requests_mem"]:
                        req_mem = req_mem / 1024
                    elif 'Mi' in pod["requests_mem"]:
                        req_mem = req_mem
                    elif 'Gi' in pod["requests_mem"]:
                        req_mem = req_mem*1024
                    elif m[2] == "":
                        req_mem = req_mem
                    else:
                        req_mem = req_mem
                    node["capacity_mem"] = int((node["capacity_mem"]*1024 - req_mem) / 1024)

                    '''storage'''
                    req_storage=0
                    storage = re.split('(\d+)',pod["requests_storage"])
                    req_storage=int(storage[1])
                    if 'Ki' in pod["requests_storage"]:
                        req_storage = req_storage / 1024 / 1024
                    elif 'Mi' in pod["requests_storage"]:
                        req_storage = req_storage / 1024
                    elif 'Gi' in pod["requests_storage"]:
                        req_storage = req_storage
                    else:
                        req_storage = req_storage
                    node["capacity_storage"] = int(node["capacity_storage"] - req_storage)
  
                    '''GPU'''
                    req_gpu=int(pod["requests_gpu"])
                    node["capacity_gpu"] = node["capacity_gpu"] - req_gpu
  
        

        self.log.info("---  Node available resources  --")
        self.log.info("{:<18} {:<8} {:<8} {:<8} {:<8}".format("NodeName","AvaCPU","AvaMem","AvaStg","AvaGPU"))
        for node in self.nodes_available:
            self.log.info("{:<18} {:<8} {:<8} {:<8} {:<8}".format(node["name"], node["capacity_cpu"], node["capacity_mem"], node["capacity_storage"], node["capacity_gpu"]))

    def get_flavor_option_lists(self):
        del self.flavor_lists[:]


        for node in self.nodes_available:    
            _node = node["name"]
            _gpu = node["capacity_gpu"]
            _cpu = node["capacity_cpu"]
            _mem = node["capacity_mem"]
            _storage = node["capacity_storage"]
            #GPU option
            flavor_inde=0
            if _gpu > 0:
                p = 1
                while p <= _gpu:
                    #print ("%20s : %d GPU option, cpu = %10d, memroy = %10d"%(_node, p, p*_cpu/_gpu, p*_mem/_gpu))
                    self.flavor_lists.append({"name":_node, 
                                              "capacity_cpu":int(p*_cpu/_gpu),
                                              "capacity_mem":int(p*_mem/_gpu),
                                              "capacity_storage":int(p*_storage/_gpu),
                                              "capacity_gpu":p})
                    p = p * 2
            #CPU option
            else:
                p = 1000
                while p <= _cpu:
                    #print ("%20s : Zero GPU option, cpu = %10d, memory = %10d"%(_node, p, p*_mem/_cpu))
                    self.flavor_lists.append({"name":_node, 
                                              "capacity_cpu":p,
                                              "capacity_mem":int(p*_mem/_cpu),
                                              "capacity_storage":int(p*_storage/_cpu),
                                              "capacity_gpu":0})
                    p = p * 2
        self.log.info("---  flavor optionm lists  --")
        for _opt in self.flavor_lists:
            self.log.info(_opt)
    # relies on HTML5 for image datalist
    def custom_form(self):
        global registry, repoName
        self.APISERVER=os.environ['KUBERNETES_SERVICE_HOST']+":"+os.environ["KUBERNETES_PORT_443_TCP_PORT"]
        with open('/var/run/secrets/kubernetes.io/serviceaccount/token','r') as f:
          self.KUBE_TOKEN = f.read()
  
        self.get_nodes_available_resources()
        self.get_flavor_option_lists()
        #self.get_nodes_list()
        #self.get_pods_list()

        #print (self.nodes_available)
        #for node in self.nodes_available:
        #  print ("node name : %20s, available cpu : %10s, memroy : %20s, gpu : %10s"%(node["name"], node["capacity_cpu"], node["capacity_mem"], node["capacity_gpu"]))
        flavor_option_table='''
    <table style="width: 100%;">
    <tr>
        <td style="width: 20%;"><label for='flavor_option'>Flavor Options</label></td>
        <td style="width: 80%;"><input list="flavor_option" name="flavor_option" placeholder='default CPU:500m; Memory:10Gi; Storage:10Gi' style="width: 100%;" autocomplete="off">
        <datalist id="flavor_option">
    '''
        for _opt in self.flavor_lists:
            if _opt["capacity_gpu"] > 0:
                flavor_option_table = flavor_option_table + '''
          <option value="node:{0};CPU:{1}m;Memory:{2}Gi;Storage:{3}Gi;GPU:{4}">
    '''.format(_opt["name"],_opt["capacity_cpu"],_opt["capacity_mem"],_opt["capacity_storage"], _opt["capacity_gpu"])
            else:
                flavor_option_table = flavor_option_table + '''
          <option value="node:{0};CPU:{1}m;Memory:{2}Gi;Storage:{3}Gi">
    '''.format(_opt["name"],_opt["capacity_cpu"],_opt["capacity_mem"],_opt["capacity_storage"])

        flavor_option_table = flavor_option_table + '''
        </datalist>
        </td>
    </tr>
    </table>
    '''

        html='''
    <table style="width: 100%;">
    <tr>
        <td style="width: 20%;"><label for='image'>Image</label></td>
        <td style="width: 80%;"><input list="image" name="image" placeholder='default:tensorflow-notebook:v1.9.0-gpu-3' style="width: 100%;" autocomplete="off">
        <datalist id="image">
          <option value="harbor.registry.com/kubeflow-images-public/faust-cudf:0.0.2">
          <option value="harbor.registry.com/kubeflow-images-public/tensorflow-notebook:v1.9.0-3">
          <option value="harbor.registry.com/kubeflow-images-public/tensorflow-notebook:v1.9.0-gpu-3">
          <option value="harbor.registry.com/kubeflow-images-public/tensorflow-notebook:ngc-18.11-py3">
        </datalist>
        </td>
    </tr>
    </table>
    <br>
    '''
        html = html + flavor_option_table + '''
    <div style="text-align: center; padding: 10px;">
      <a id="toggle_advanced_options" style="margin: 20%; cursor: pointer; font-weight: bold;">Advanced</a>
    </div>
    <table id="advanced_fields" style="display: none; width: 100%; border-spacing: 0px 25px; border-collapse: separate;">
    <tr>
      <td><label for='cpu_limit'>CPU Limit</label></td>
      <td><input style="width: 100%;" name='cpu_limit' placeholder='200m, 1.0, 2.5, etc, default 500m' class="resource_limit" id="cpu_resource"></input></td>
    </tr>
    <tr>
      <td><label for='mem_limit'>Memory Limit</label></td>
      <td><input style="width: 100%;" name='mem_limit' placeholder='100Mi, 1.5Gi, default 10Gi' class="resource_limit" id="mem_resource"></input></td>
    </tr>
    <tr>
      <td><label for='stg_limit'>Local Storage Limit</label></td>
      <td><input style="width: 100%;" name='stg_limit' placeholder='5Gi, default 5Gi' class="resource_limit" id="stg_resource"></input></td>
    </tr>
    <tr>
      <td><label for='gpu_limit'>GPU Limit</label></td>
      <td><input style="width: 100%;" name='gpu_limit' placeholder='1, default 0' class="resource_limit" id="gpu_resource"></input></td>
    </tr>
    <tr>
        <td><label for='registry_secret'>registry secret</label></td>
        <td><input style="width: 100%;" name='registry_secret' placeholder='None'></input></td>
    </tr>
    </table>'''  #.format(self.nodes_available[0]["capacity_cpu"],self.nodes_available[0]["capacity_mem"],self.nodes_available[0]["capacity_gpu"] )


        capacity_table='''
    <div id="resource_fields" style="display: none; height:200px; overflow-y: scroll;">
    <table id="resource_table" style="width: 100%; border-spacing: 0px 25px; border-collapse: separate;">
    <tr>
      <!--<td style="width: 25%; display: none;"></td>-->
      <td style="width: 25%;"><label>Node Available Resources</label></td>
      <td style="width: 25%;"></td>
      <td style="width: 25%;"></td>
      <td style="width: 25%;"></td>
      <td style="width: 25%;"></td>
    </tr>
    <tr>
      <td><label>Node Name</label></td>
      <td><label>CPU</label></td>
      <td><label>Memory</label></td>
      <td><label>Storage</label></td>
      <td><label>GPU</label></td>
    </tr>
    '''
        for node in self.nodes_available:
          capacity_table = capacity_table + '''
    <tr>
      <td>{0}</td>
      <td>{1}m</td>
      <td>{2}Gi</td>
      <td>{3}Gi</td>
      <td>{4}</td>
    </tr>'''.format(node["name"], node["capacity_cpu"], node["capacity_mem"], node["capacity_storage"], node["capacity_gpu"])


        html = html + capacity_table + '''
    </table>
    </div>
    '''
        capacity_list='''var node_capacity = ['''
        for node in self.nodes_available:
          #print ("node name = %s"%(node["name"]))
          capacity_list = capacity_list + "{" + '''name: "{0}", capacity_cpu:"{1}", capacity_mem:"{2}", capacity_stg:"{3}", capacity_gpu:"{4}"'''.format(node["name"], node["capacity_cpu"], node["capacity_mem"], node["capacity_storage"], node["capacity_gpu"]) + "},"
        capacity_list = capacity_list + "];"

        html = html + '''
    <script type="text/javascript">
      $('#toggle_advanced_options').on('click', function(e){{
        $('#advanced_fields').toggle();
        $('#resource_fields').toggle();
      }});
      $('.resource_limit').on('change', function(e){{
        var cpu = document.getElementById("cpu_resource").value;
        var mem = document.getElementById("mem_resource").value;
        var stg = document.getElementById("stg_resource").value;
        var gpu = document.getElementById("gpu_resource").value;
        '''+capacity_list+'''
        var have_cpu = false;
        var have_mem = false;
        var have_gpu = false;
        var have_storage = false;
        var have_avail_node = false;

        if (cpu == "")
          cpu = "500m";
        if (mem == "")
          mem = "10Gi";
        if (stg == "")
          stg = "5Gi";
        if (gpu == "")
          gpu = "0";
        
        var cpu_str = cpu.split(/([0-9]+)/);
        var mem_str = mem.split(/([0-9]+)/);
        var stg_str = stg.split(/([0-9]+)/);
        var cpu_digit = Number(cpu_str[1]);
        var cpu_unit = cpu_str[2];
        var mem_digit = Number(mem_str[1]);
        var mem_unit = mem_str[2];
        var stg_digit = Number(stg_str[1]);
        var stg_unit = stg_str[2];

        console.log("cpu_str = %s", cpu_str);
        console.log("mem_str = %s", mem_str);
        console.log("cpu digit = %d", cpu_digit);
        console.log("cpu unit = %s", cpu_unit);
        console.log("mem digit = %d", mem_digit);
        console.log("mem unit = %s", mem_unit);
        console.log("stg digit = %d", stg_digit);
        console.log("stg unit = %s", stg_unit);
        console.log("gpu = %s", gpu)

        var cpu_value = 0;
        var mem_value = 0;

        var gpu_value = Number(gpu);
        if (cpu_unit == "")  //user enter cores
          cpu_value = cpu_digit * 1000;
        else if (cpu_unit == "m")
          cpu_value = cpu_digit;
        else if (cpu_unit == ".")
          cpu_value = Number(cpu) * 1024;
        else
          alert("Please enter CPU with format : 200m, 1.0, 2.5, etc");  

        if (mem_unit == "Mi")
          mem_value = mem_digit / 1024;
        else if (mem_unit == "Gi")
          mem_value = mem_digit;
        else
          alert("Please enter Memory with format : 100Mi, 1.5Gi, etc"); 

        if (stg_unit == "Mi")
          stg_value = stg_digit/1024;
        else if (stg_unit == "Gi")
          stg_value = stg_digit;
        else
          alert("Please enter Storage with format : 5Gi, etc"); 

        //if ( gpu.indexOf("nvidia.com/gpu") > -1 )  
        //{ 
        //  var res = gpu.split("}");
        //  var res = res[0].split(":")
        //  gpu_value = Number(res[1]);
        //}
        //else if (gpu == "") 
        //{
        //  console.log("no extra resource limits");
        //  gpu_value = 0;
        //}
        //else
        //  alert("Please enter Extra Resource Limits with format : {nvidia.com/gpu:N}"); 

        console.log("cpu value = %d m", cpu_value);
        console.log("mem value = %d Mi", mem_value);
        console.log("storage value = %d Gi", stg_value)
        console.log("gpu value = %d", gpu_value);

        for (var i = 0; i < node_capacity.length; i++)
        {
          var node_name = node_capacity[i].name;
          var node_capacity_cpu = Number(node_capacity[i].capacity_cpu);
          var node_capacity_mem = Number(node_capacity[i].capacity_mem);
          var node_capacity_gpu = Number(node_capacity[i].capacity_gpu);
          console.log("node :%s, have cpu : %d, mem : %d, gpu : %d, current require cpu : %d, mem : %d, gpu : %d", node_name, node_capacity_cpu, node_capacity_mem, node_capacity_gpu, cpu_value, mem_value, gpu_value);
          if (cpu_value <= node_capacity_cpu && mem_value <= node_capacity_mem && gpu_value <= node_capacity_gpu) 
          {
            have_avail_node = true;
            console.log("node "+node_name+" have available resource");
          }
        }
        if (have_avail_node == false)
          alert("Required resources not available");
      }});
    </script>  
    '''

        #print (html)

        return html


    # relies on HTML5 for image datalist
    def _options_form_default(self):
        self.log.info("_options_form_default")
        html = self.custom_form()
        return html

    async def get_options_form(self):
        self.log.info("get_options_form~~~~~~~~~~~")

        self.options_form = self._options_form_default()
        #self.log.info("self.options_form = %s", self.options_form)
        return self.options_form

    def options_from_form(self, formdata):
        options = {}

        self.log.info("formdata = %s"%(formdata))

        options['image']      = formdata.get('image',[''])[0].strip()
        options['flavor']     = formdata.get('flavor_option',[''])[0].strip()
        options['cpu_limit']  = formdata.get('cpu_limit',[''])[0].strip()
        options['mem_limit']  = formdata.get('mem_limit',[''])[0].strip()
        options['stg_limit']  = formdata.get('stg_limit',[''])[0].strip()
        options['gpu_limit']  = formdata.get('gpu_limit', [''])[0].strip()
        options['registry_secret']       = formdata.get('registry_secret', [''])[0].strip()

        image = options['image'].split('/')[-1]
        self.log.info("image = %s" % image)
        self.log.info("flavor options = %s"%(options['flavor']))
        if image.find('potato') != -1:
            num_cores = 4
            mem = 10
            num_gpus = 0
            specs = image.split('-')
            for spec in specs:
                if spec.find('cpu') != -1:
                    num_cores = int(spec.split('cpu')[1])
                if spec.find('mem') != -1:
                    mem = int(spec.split('mem')[1])
                if spec.find('gpu') != -1:
                    num_gpus = int(spec.split('gpu')[1])

            options['cpu_limit'] = '%d' % num_cores
            options['mem_limit'] = '%dGi' % mem
            options['stg_limit'] = '5Gi'
            options['gpu_limit'] = num_gpus

        elif options['cpu_limit']=="" and options['mem_limit']=="" and options['stg_limit']=="" and options['gpu_limit']=="" and options['flavor']:
            # 'node:kubeflow-vm-0;CPU:2120m;Memory:67Gi;Storage:27Gi;GPU:1'
            self.log.info("Not select resources and selece flavor: use flavor")
            _flavor_list=options['flavor'].split(";")
            self.log.info("flavor list = %s"%(_flavor_list))
            _flavor_dict={}
            for i in _flavor_list:
                _tmp = i.split(":")
                _flavor_dict[_tmp[0]]=_tmp[1]
            options["node_selector"] = _flavor_dict["node"]
            options['cpu_limit']     = _flavor_dict["CPU"]
            options["mem_limit"]     = _flavor_dict["Memory"]
            options["stg_limit"]     = _flavor_dict["Storage"]
            if 'GPU' in options['flavor']:
                options["gpu_limit"]     = _flavor_dict["GPU"]
            else:
                options["gpu_limit"] = 0
        else:
            options['cpu_guarantee'] = formdata.get(
                'cpu_guarantee', [''])[0].strip()
            options['mem_guarantee'] = formdata.get(
                'mem_guarantee', [''])[0].strip()
            options['extra_resource_limits'] = formdata.get(
                'extra_resource_limits', [''])[0].strip()

        self.log.info("options = %s"%(options)) 

        if options['gpu_limit']:
            self.log.info("##nvidia.com = %s"%(int(options['gpu_limit'])))
            gpu_request_num = int(options['gpu_limit'])
            if gpu_request_num > 0:
                self.gpuAllocate=True
            else:
                self.gpuAllocate=False
        else:
            self.gpuAllocate=False
            self.log.info("@@allocate GPU False")
        
        #if 'nvidia.com/gpu' in options['gpu_limit']:
        #    self.log.info("options have nvidia.com/gpu")
        #    _extra = json.loads(options['extra_resource_limits'])
        #    self.log.info("_extra = %s"%(_extra))
        #    gpu_request_num = int(_extra['nvidia.com/gpu'])
        #    self.log.info("##nvidia.com = %s"%(gpu_request_num) )
        #    if gpu_request_num > 0:
        #        self.log.info("@@allocate GPU True")
        #        self.gpuAllocate=True
        #else:
        #    self.gpuAllocate=False
        #    self.log.info("@@allocate GPU False")
        
        return options

    @property
    def singleuser_image_spec(self):
        global cloud
        if cloud == 'ack':
            image = 'registry.aliyuncs.com/kubeflow-images-public/tensorflow-notebook-cpu:v0.2.1'
        else:
            image = 'gcr.io/kubeflow-images-public/tensorflow-1.8.0-notebook-cpu:v0.3.1'
        if self.user_options.get('image'):
            image = self.user_options['image']
        else:  #default image
            image = "harbor.registry.com/kubeflow-images-public/tensorflow-notebook:v1.9.0-gpu-3"
        return image

    image_spec = singleuser_image_spec

    @property
    def cpu_guarantee(self):
        cpu = '500m'
        if self.user_options.get('cpu_limit'):
            cpu = self.user_options['cpu_limit']
        return cpu

    @property
    def cpu_limit(self):
        cpu = '500m'
        if self.user_options.get('cpu_limit'):
            cpu = self.user_options['cpu_limit']
        return cpu

    @property
    def mem_guarantee(self):
        mem = '10Gi'
        if self.user_options.get('mem_limit'):
            mem = self.user_options['mem_limit']
        return mem

    @property
    def mem_limit(self):
        mem = '10Gi'
        if self.user_options.get('mem_limit'):
            mem = self.user_options['mem_limit']
        return mem

    @property
    def extra_resource_limits(self):
        extra = {}
        self.gpuAllocate=False

        if self.user_options.get('gpu_limit'):
            gpu_request_num = int(self.user_options.get('gpu_limit'))
            if gpu_request_num > 0:
                self.gpuAllocate=True
                extra["nvidia.com/gpu"] = gpu_request_num
            else:
                self.gpuAllocate=False

        storage='5Gi'
        if self.user_options.get('stg_limit'):
            storage = self.user_options['stg_limit']
        extra["ephemeral-storage"]=storage

        self.log.info("############## extra_resource_limits = %s "%(extra))
        return extra

    @property
    def image_pull_secrets(self):
        secret = None
        if self.user_options.get('registry_secret'):
            secret = self.user_options['registry_secret']
        return secret

    @property
    def node_selector(self):
        self.log.info("@@property node selector...")
        if self.user_options.get('node_selector'):
            nodeSelector={}
            nodeName = self.user_options.get('node_selector')
            nodeSelector['kubernetes.io/hostname']=nodeName
            return nodeSelector
        else: 
            return None

    def get_env(self):
        env = super(KubeFormSpawner, self).get_env()
        gcp_secret_name = os.environ.get('GCP_SECRET_NAME')
        if gcp_secret_name:
            env['GOOGLE_APPLICATION_CREDENTIALS'] = '{}/{}.json'.format(SERVICE_ACCOUNT_SECRET_MOUNT, gcp_secret_name)
        self.log.info('get_env check self.gpuAllocate = %s'%(self.gpuAllocate))
        if self.gpuAllocate == False:
            env['NVIDIA_VISIBLE_DEVICES'] = 'none'

        return env

    # TODO(kkasravi): add unit test
    def _parse_user_name(self, username):
        safe_chars = set(string.ascii_lowercase + string.digits)
        name = username.split(':')[-1]
        legacy = ''.join([s if s in safe_chars else '-' for s in name.lower()])
        safe = escapism.escape(name, safe=safe_chars, escape_char='-').lower()
        return legacy, safe, name

    def _expand_user_properties(self, template):
        # override KubeSpawner method to remove prefix accounts.google: for iap
        # and truncate to 63 characters

        # Set servername based on whether named-server initialised
        if self.name:
            servername = '-{}'.format(self.name)
        else:
            servername = ''

        legacy, safe, name = self._parse_user_name(self.user.name)
        rname = template.format(
            userid=self.user.id,
            username=safe,
            unescaped_username=name,
            legacy_escape_username=legacy,
            servername=servername
            )[:63]
        return rname


###################################################
# JupyterHub Options
###################################################
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.hub_ip = '0.0.0.0'
# Don't try to cleanup servers on exit - since in general for k8s, we want
# the hub to be able to restart without losing user containers
c.JupyterHub.cleanup_servers = False
###################################################

# Set the Jupyterhub log file location
c.JupyterHub.extra_log_file = '/var/log/jupyterhub.log'
# Set the log level by value or name.
c.JupyterHub.log_level = 'DEBUG'

###################################################
# Spawner Options
###################################################
cloud = os.environ.get('CLOUD_NAME')
registry = os.environ.get('REGISTRY')
repoName = os.environ.get('REPO_NAME')
c.JupyterHub.spawner_class = KubeFormSpawner
# Set both singleuser_image_spec and image_spec because
# singleuser_image_spec has been deprecated in a future release
c.KubeSpawner.singleuser_image_spec = '{0}/{1}/tensorflow-notebook'.format(registry, repoName)
c.KubeSpawner.image_spec = '{0}/{1}/tensorflow-notebook'.format(registry, repoName)

working_dir=os.environ.get('NOTEBOOK_WORK_DIR')   # default /notebooks

c.KubeSpawner.cmd = 'start-singleuser.sh'
c.KubeSpawner.args = ['--allow-root']
# gpu images are very large ~15GB. need a large timeout.
c.KubeSpawner.start_timeout = 60 * 10
# Increase timeout to 5 minutes to avoid HTTP 500 errors on JupyterHub
c.KubeSpawner.http_timeout = 60 * 5

##################################################
# environment set
c.KubeSpawner.environment = {"GRANT_SUDO":"yes", "NOTEBOOK_WORK_DIR":working_dir, "NB_GID":"1000"}

pvc_mount = os.environ.get('NOTEBOOK_PVC_MOUNT')
if pvc_mount and pvc_mount != 'null':
    c.KubeSpawner.environment["NOTEBOOK_PVC_DIR"]=pvc_mount

vdb_mount = os.environ.get('NOTEBOOK_VDB_MOUNT')
if vdb_mount and vdb_mount != 'null':
    c.KubeSpawner.environment["NOTEBOOK_DATA_DIR"]=vdb_mount

delete_local_data=os.environ['MULTI_NODE_CLUSTER']
if delete_local_data == "MULTI_NODE_CLUSTER":
    c.KubeSpawner.environment["NOTEBOOK_DELETE_LOCAL_DATA"]="DELETE_LOCAL_DATA"
##################################################

# Volume setup
c.KubeSpawner.singleuser_uid = 0 #1000
c.KubeSpawner.singleuser_fs_gid = 0 #100
c.KubeSpawner.singleuser_working_dir = working_dir #'/home/jovyan'
volumes = []
volume_mounts = []

# Allow environment vars to override uid and gid.
# This allows local host path mounts to be read/writable
env_uid = os.environ.get('NOTEBOOK_UID')
if env_uid:
    c.KubeSpawner.singleuser_uid = int(env_uid)
env_gid = os.environ.get('NOTEBOOK_GID')
if env_gid:
    c.KubeSpawner.singleuser_fs_gid = int(env_gid)
access_local_fs = os.environ.get('ACCESS_LOCAL_FS')
if access_local_fs == 'true':
    def modify_pod_hook(spawner, pod):
       pod.spec.containers[0].lifecycle = {
            'postStart' : {
               'exec' : {
                   'command' : ['ln', '-s', '/mnt/local-notebooks', '/home/jovyan/local-notebooks' ]
               }
            }
        }
       return pod
    c.KubeSpawner.modify_pod_hook = modify_pod_hook

###################################################
# Persistent volume options
###################################################
# Using persistent storage requires a default storage class.
# TODO(jlewi): Verify this works on minikube.
# see https://github.com/kubeflow/kubeflow/pull/22#issuecomment-350500944
pvc_mount = os.environ.get('NOTEBOOK_PVC_MOUNT')
if pvc_mount and pvc_mount != 'null':
    c.KubeSpawner.user_storage_pvc_ensure = True
    c.KubeSpawner.storage_pvc_ensure = True
    # How much disk space do we want?
    c.KubeSpawner.user_storage_capacity = '10Gi'
    c.KubeSpawner.storage_capacity = '10Gi'
    c.KubeSpawner.pvc_name_template = 'claim-{username}{servername}'
    volumes.append(
        {
            'name': 'volume-{username}{servername}',
            'persistentVolumeClaim': {
                'claimName': 'claim-{username}{servername}'
            }
        }
    )
    volume_mounts.append(
        {
            'mountPath': pvc_mount,
            'name': 'volume-{username}{servername}'
        }
    )

# ###################################################
# ### Extra volumes
# ###################################################
vdb_mount = os.environ.get('NOTEBOOK_VDB_MOUNT')
if vdb_mount and vdb_mount != 'null':
  localPath='/mnt/local-{username}'
  volumes.append(
  {
      'name': 'local-ssd',
      'hostPath' : {
          'path': localPath
      }
  })
  volume_mounts.append(
    {
      'name': 'local-ssd',
      'mountPath': vdb_mount
    }
  )


c.KubeSpawner.volumes = volumes
c.KubeSpawner.volume_mounts = volume_mounts
# Set both service_account and singleuser_service_account because
# singleuser_service_account has been deprecated in a future release
c.KubeSpawner.service_account = 'jupyter-notebook'
c.KubeSpawner.singleuser_service_account = 'jupyter-notebook'
# Authenticator

if os.environ.get('KF_AUTHENTICATOR') == 'iap':
    c.JupyterHub.authenticator_class ='jhub_remote_user_authenticator.remote_user_auth.RemoteUserAuthenticator'
    c.RemoteUserAuthenticator.header_name = 'x-goog-authenticated-user-email'
elif os.environ.get('KF_AUTHENTICATOR') == 'ldap':
    c.JupyterHub.authenticator_class = 'ldapauthenticator.LDAPAuthenticator'
    c.LDAPAuthenticator.server_address = os.environ.get('LDAP_AUTHENTICATOR_IP')
    c.LDAPAuthenticator.user_attribute = 'uid'
    c.LDAPAuthenticator.bind_dn_template = os.environ.get('LDAP_AUTHENTICATOR_TMP_DN')
else:
    c.JupyterHub.authenticator_class = 'dummyauthenticator.DummyAuthenticator'

if os.environ.get('DEFAULT_JUPYTERLAB').lower() == 'true':
    c.KubeSpawner.default_url = '/lab'

# PVCs
pvcs = os.environ.get('KF_PVC_LIST')
if pvcs and pvcs != 'null':
    for pvc in pvcs.split(','):
        volumes.append({
            'name': pvc,
            'persistentVolumeClaim': {
                'claimName': pvc
            }
        })
        volume_mounts.append({
            'name': pvc,
            'mountPath': '/mnt/' + pvc
        })

gcp_secret_name = os.environ.get('GCP_SECRET_NAME')
if gcp_secret_name:
    volumes.append({
      'name': gcp_secret_name,
      'secret': {
        'secretName': gcp_secret_name,
      }
    })
    volume_mounts.append({
        'name': gcp_secret_name,
        'mountPath': SERVICE_ACCOUNT_SECRET_MOUNT
    })

