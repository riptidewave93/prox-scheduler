-- phpMyAdmin SQL Dump
-- version 4.6.6
-- https://www.phpmyadmin.net/
--
-- Host: db
-- Generation Time: Mar 19, 2017 at 11:54 AM
-- Server version: 10.1.21-MariaDB-1~jessie
-- PHP Version: 7.0.15

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";

--
-- Database: `prox-scheduler`
--
CREATE DATABASE IF NOT EXISTS `prox-scheduler` DEFAULT CHARACTER SET latin1 COLLATE latin1_swedish_ci;
USE `prox-scheduler`;

-- --------------------------------------------------------

--
-- Table structure for table `instances`
--

CREATE TABLE `instances` (
  `id` int(11) NOT NULL,
  `uuid` varchar(36) NOT NULL,
  `state` int(2) NOT NULL,
  `hostname` varchar(128) NOT NULL,
  `memory` int(8) NOT NULL,
  `cpu` int(4) NOT NULL,
  `disk` int(16) NOT NULL,
  `ip` varchar(16) DEFAULT NULL,
  `backend_storage` varchar(32) DEFAULT NULL,
  `backend_hypervisor` varchar(32) DEFAULT NULL,
  `backend_instance_id` int(11) DEFAULT NULL,
  `backend_build_state` varchar(8) DEFAULT NULL,
  `template_id` int(11) NOT NULL,
  `userdata_id` int(11) DEFAULT NULL,
  `downloads` varchar(32768) DEFAULT NULL,
  `created` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Dumping data for table `instances`
--

-- --------------------------------------------------------

--
-- Table structure for table `instance_states`
--

CREATE TABLE `instance_states` (
  `id` int(11) NOT NULL,
  `name` varchar(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Dumping data for table `instance_states`
--

INSERT INTO `instance_states` (`id`, `name`) VALUES
(1, 'Create Submitted'),
(2, 'Create Scheduled'),
(3, 'Building'),
(4, 'Resizing'),
(5, 'Powering On'),
(6, 'Provisioning'),
(7, 'Running Build'),
(8, 'Deployed'),
(9, 'Downloading'),
(10, 'Compressing'),
(11, 'Build Complete'),
(12, 'Build Failed'),
(20, 'Destroy Submitted'),
(21, 'Destroy Scheduled'),
(22, 'Powering Off'),
(23, 'Destroying'),
(24, 'Destroyed'),
(50, 'Unexpected Error');

-- --------------------------------------------------------

--
-- Table structure for table `instance_userdata`
--

CREATE TABLE `instance_userdata` (
  `id` int(11) NOT NULL,
  `instance_uuid` varchar(36) NOT NULL,
  `userdata` mediumtext CHARACTER SET utf8
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Dumping data for table `instance_userdata`
--

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `id` int(11) NOT NULL,
  `username` varchar(32) NOT NULL,
  `password` varchar(40) NOT NULL,
  `email` varchar(128) NOT NULL,
  `is_active` int(1) NOT NULL DEFAULT '0'
) ENGINE=InnoDB DEFAULT CHARSET=latin1;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`id`, `username`, `password`, `email`, `is_active`) VALUES
(1, 'admin', 'f8a0ccbc1b865bec714d88586a211d29b51a26e2', 'admin@site.com', 0);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_instances`
-- (See below for the actual view)
--
CREATE TABLE `v_instances` (
`id` int(11)
,`uuid` varchar(36)
,`state` varchar(16)
,`hostname` varchar(128)
,`memory` int(8)
,`cpu` int(4)
,`disk` int(16)
,`ip` varchar(16)
,`backend_storage` varchar(32)
,`backend_hypervisor` varchar(32)
,`backend_instance_id` int(11)
,`template_id` int(11)
,`userdata` mediumtext
,`downloads` varchar(32768)
,`created` timestamp
);

-- --------------------------------------------------------

--
-- Structure for view `v_instances`
--
DROP TABLE IF EXISTS `v_instances`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`%` SQL SECURITY DEFINER VIEW `v_instances`  AS  select `i`.`id` AS `id`,`i`.`uuid` AS `uuid`,`s`.`name` AS `state`,`i`.`hostname` AS `hostname`,`i`.`memory` AS `memory`,`i`.`cpu` AS `cpu`,`i`.`disk` AS `disk`,`i`.`ip` AS `ip`,`i`.`backend_storage` AS `backend_storage`,`i`.`backend_hypervisor` AS `backend_hypervisor`,`i`.`backend_instance_id` AS `backend_instance_id`,`i`.`backend_build_state` AS `backend_build_state`,`i`.`template_id` AS `template_id`,`u`.`userdata` AS `userdata`,`i`.`downloads` AS `downloads`,`i`.`created` AS `created` from ((`instances` `i` left join `instance_states` `s` on((`i`.`state` = `s`.`id`))) left join `instance_userdata` `u` on((`i`.`userdata_id` = `u`.`id`))) ;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `instances`
--
ALTER TABLE `instances`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `instance_states`
--
ALTER TABLE `instance_states`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `instance_userdata`
--
ALTER TABLE `instance_userdata`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `instances`
--
ALTER TABLE `instances`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;
--
-- AUTO_INCREMENT for table `instance_states`
--
ALTER TABLE `instance_states`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=13;
--
-- AUTO_INCREMENT for table `instance_userdata`
--
ALTER TABLE `instance_userdata`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;
--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;
