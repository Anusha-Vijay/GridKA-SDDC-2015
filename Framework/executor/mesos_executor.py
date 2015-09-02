#!/usr/bin/env python
import SimpleHTTPServer
import SocketServer
import sys
import logging
import threading
import uuid
import signal
import time

from mesos.interface import Scheduler, mesos_pb2
from mesos.native import MesosSchedulerDriver

logging.basicConfig(level=logging.INFO)
TASK_CPUS = 0.1
TASK_MEM = 256


def new_task(offer, name):
    task = mesos_pb2.TaskInfo()
    task.task_id.value = str(uuid.uuid4())
    task.slave_id.value = offer.slave_id.value
    task.name = name

    cpus = task.resources.add()
    cpus.name = "cpus"
    cpus.type = mesos_pb2.Value.SCALAR
    cpus.scalar.value = TASK_CPUS

    mem = task.resources.add()
    mem.name = "mem"
    mem.type = mesos_pb2.Value.SCALAR
    mem.scalar.value = TASK_MEM

    return task


def max_tasks_to_run_with_offer( offer):
    logging.info("CPUs: %s MEM: %s",
                 offer.resources[0].scalar.value,
                 offer.resources[1].scalar.value)

    cpu_tasks = int(offer.resources[0].scalar.value/TASK_CPUS)
    mem_tasks = int(offer.resources[1].scalar.value/TASK_MEM)

    return cpu_tasks if cpu_tasks <= mem_tasks else mem_tasks


class HelloWorldScheduler(Scheduler):
    def __init__(self, hello_executor):
        self.runningTasks = 0
        self.hello_executor = hello_executor

    def registered(self, driver, framework_id, master_info):
        logging.info("Registered with framework id: %s on: %s",
                     framework_id, master_info.hostname)

    def resourceOffers(self, driver, offers):
        logging.info("Recieved resource offers: %s",
                     [o.id.value for o in offers])
        for offer in offers:
            def handle_offer():
                count_tasks = max_tasks_to_run_with_offer(offer)
                logging.info("Count Tasks: %s", count_tasks)
                if count_tasks == 0:
                    logging.info("Decline Offer %s", offer.id)
                    driver.declineOffer(offer.id)
                    return

                tasks = []
                for i in range(count_tasks / 2):
                    task = new_task(offer, "Hello ")
                    task.executor.MergeFrom(self.hello_executor)
                    logging.info("Added task %s "
                                 "using offer %s.",
                                 task.task_id.value,
                                 offer.id.value)
                    tasks.append(task)
                logging.info("Launch %s Tasks", len(tasks))
                driver.launchTasks(offer.id, tasks)
            threading.Thread(target=handle_offer).start()

    def statusUpdate(self, driver, update):
        '''
        when a task is started, over,
        killed or lost (slave crash, ....), this method
        will be triggered with a status message.
        '''
        logging.info("Task %s is in state %s" %
                     (update.task_id.value,
                      mesos_pb2.TaskState.Name(update.state)))

        if update.state == mesos_pb2.TASK_RUNNING:
            self.runningTasks += 1
            logging.info("Running tasks: %s", self.runningTasks)
            return

        if update.state != mesos_pb2.TASK_RUNNING or\
           update.state != mesos_pb2.TASK_STARTING or\
           update.state != mesos_pb2.TASK_STAGING:
            self.runningTasks -= 1
            logging.info("Running tasks: %s", self.runningTasks)


def shutdown(signal, frame):
    logging.info("Shutdown signal")
    driver.stop()
    httpd.stop()
    sys.exit(0)

if __name__ == '__main__':
    hello_executor = mesos_pb2.ExecutorInfo()
    hello_executor.executor_id.value = "hello-executor"
    hello_executor.name = "Hello"
    hello_executor.command.value = "python hello_executor.py"

    uri_proto = hello_executor.command.uris.add()
    uri_proto.value = "http://kit-mesos-master:9000/hello_executor.py"
    uri_proto.extract = False

    framework = mesos_pb2.FrameworkInfo()
    framework.user = ""  # Have Mesos fill in the current user.
    framework.name = "hello-world"

    httpd = SocketServer.TCPServer(
        ("", 9000),
        SimpleHTTPServer.SimpleHTTPRequestHandler)

    def create_web_server():
        print "serving at port", 9000
        httpd.serve_forever()
    thread = threading.Thread(target=create_web_server)
    thread.start()

    driver = MesosSchedulerDriver(
        HelloWorldScheduler(hello_executor),
        framework,
        "zk://localhost:2181/mesos"
    )
    driver.start()
    logging.info("Listening for Ctrl-C")
    signal.signal(signal.SIGINT, shutdown)
    while True:
        time.sleep(5)
    sys.exit(0)
