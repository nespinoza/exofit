# -*- coding: utf-8 -*-
from math import floor,ceil
import matplotlib.pyplot as plt
import numpy as np
import batman

def get_sigma(x,median):
    """
    This function returns the MAD-based standard-deviation.
    """
    mad = np.median(np.abs(x-median))
    return 1.4826*mad

def get_phases(t,P,t0):
    phase = ((t - np.median(t0))/np.median(P)) % 1
    ii = np.where(phase>=0.5)[0]
    phase[ii] = phase[ii]-1.0
    return phase

def read_transit_params(prior_dict,instrument):
    names = ['P','inc','a','p','t0','q1','q2']
    vals = len(names)*[[]]
    for i in range(len(names)):
        try:
            param = prior_dict[names[i]]
        except:
            param = prior_dict[names[i]+'_'+instrument]
        vals[i] = param['object'].value
    return vals

def pre_process(all_t,all_f,all_f_err,options,transit_instruments,parameters):#detrend,get_outliers,n_ommit,window,parameters,ld_law,mode):
    all_phases = np.zeros(len(all_t))
    for instrument in options['photometry'].keys():
        all_idx = np.where(transit_instruments==instrument)[0]
        t = all_t[all_idx]
        f = all_f[all_idx]
        if all_f_err is not None:
            f_err = all_f_err[all_idx]
        
        # Now, the first phase in transit fitting is to 'detrend' the 
        # data. This is done with the 'detrend' flag. If 
        # the data is already detrended, set the flag to None:
        if options['photometry'][instrument]['PHOT_DETREND'] is not None:
            if options['photometry'][instrument]['PHOT_DETREND'] == 'mfilter':
                # Get median filter, and smooth it with a gaussian filter:
                from scipy.signal import medfilt
                from scipy.ndimage.filters import gaussian_filter
                filt = gaussian_filter(medfilt(f,window),5)
                f = f/filt
                if f_err is not None:
                    f_err = f_err/filt

        # Extract transit parameters from prior dictionary:
        P,inc,a,p,t0,q1,q2 = read_transit_params(parameters,instrument)

        # If the user wants to ommit transit events:
        if len(options['photometry'][instrument]['NOMIT'])>0:
            # Get the phases:
            phases = (t-t0)/P

            # Get the transit events in phase space:
            transit_events = np.arange(ceil(np.min(phases)),floor(np.max(phases))+1)

            # Convert to zeros fluxes at the events you want to eliminate:
            for n in options['photometry'][instrument]['NOMIT']:
                idx = np.where((phases>n-0.5)&(phases<n+0.5))[0]
                f[idx] = np.zeros(len(idx))

            # Eliminate them from the t,f and phases array:
            idx = np.where(f!=0.0)[0]
            t = t[idx]
            f = f[idx]
            phases = phases[idx]
            if f_err is not None:
                f_err = f_err[idx]

        if options['MODE'] == 'transit_noise':
            # Get the phases:
            phases = (t-t0)/P

            # Get the transit events in phase space:
            transit_events = np.arange(ceil(np.min(phases)),floor(np.max(phases))+1)

            for n in transit_events:
                idx = np.where((phases>n-0.01)&(phases<n+0.01))[0]
                f[idx] = np.zeros(len(idx))

            # Eliminate them from the t,f and phases array:
            idx = np.where(f!=0.0)[0]
            t = t[idx]
            f = f[idx]
            phases = phases[idx]
            if f_err is not None:
                f_err = f_err[idx]

        # Generate the phases:
        phases = get_phases(t,P,t0)
        # If outlier removal is on, remove them:
        if options['photometry'][instrument]['PHOT_GET_OUTLIERS']:
            model = get_transit_model(t.astype('float64'),t0,P,p,a,inc,q1,q2,options['photometry'][instrument]['LD_LAW'])
            # Get approximate transit duration in phase space:
            idx = np.where(model == 1.0)[0]
            phase_dur = np.abs(phases[idx][np.where(np.abs(phases[idx]) == \
                               np.min(np.abs(phases[idx])))])[0] + 0.01

            # Get precision:
            median_flux = np.median(f)
            sigma = get_sigma(f,median_flux)
            # Perform sigma-clipping for out-of-transit data using phased data:
            good_times = np.array([])
            good_fluxes = np.array([])
            good_phases = np.array([])
            if f_err is not None:
                good_errors = np.array([])

            # Iterate through the dataset:
            for i in range(len(t)):
                    if np.abs(phases[i])<phase_dur:
                            good_times = np.append(good_times,t[i])
                            good_fluxes = np.append(good_fluxes,f[i])
                            good_phases = np.append(good_phases,phases[i])
                            if f_err is not None:
                               good_errors = np.append(good_errors,f_err[i])
                    else:
                            if (f[i]<median_flux + 3*sigma) and (f[i]>median_flux - 3*sigma):
                                    good_times = np.append(good_times,t[i])
                                    good_fluxes = np.append(good_fluxes,f[i])
                                    good_phases = np.append(good_phases,phases[i])
                                    if f_err is not None:
                                        good_errors = np.append(good_errors,f_err[i])
            t = good_times
            f = good_fluxes
            phases = good_phases
            if f_err is not None:
                f_err = good_errors
        all_t[all_idx] = t
        all_f[all_idx] = f 
        all_f_err[all_idx] = f_err
        all_phases[all_idx] = phases

    if f_err is not None:
       return all_t.astype('float64'), all_phases.astype('float64'), all_f.astype('float64'), all_f_err.astype('float64')
    else:
       return all_t.astype('float64'), all_phases.astype('float64'), all_f.astype('float64'), f_err

def init_batman(t,law):
    """
    This function initializes the batman code.
    """
    params = batman.TransitParams()
    params.t0 = 0.
    params.per = 1.
    params.rp = 0.1
    params.a = 15.
    params.inc = 87.
    params.ecc = 0.
    params.w = 90.
    params.u = [0.1,0.3]
    params.limb_dark = law
    m = batman.TransitModel(params,t)
    return params,m

def get_transit_model(t,t0,P,p,a,inc,q1,q2,ld_law):
    params,m = init_batman(t,law=ld_law)
    coeff1,coeff2 = reverse_ld_coeffs(ld_law, q1, q2)
    params.t0 = t0
    params.per = P
    params.rp = p
    params.a = a
    params.inc = inc
    params.u = [coeff1,coeff2]
    return m.light_curve(params)

def convert_ld_coeffs(ld_law, coeff1, coeff2):
    if ld_law == 'quadratic':
        q1 = (coeff1 + coeff2)**2
        q2 = coeff1/(2.*(coeff1+coeff2))
    elif ld_law=='squareroot':
        q1 = (coeff1 + coeff2)**2
        q2 = coeff2/(2.*(coeff1+coeff2))
    elif ld_law=='logarithmic':
        q1 = (1-coeff2)**2
        q2 = (1.-coeff1)/(1.-coeff2)
    return q1,q2

def reverse_ld_coeffs(ld_law, q1, q2):
    if ld_law == 'quadratic':
        coeff1 = 2.*np.sqrt(q1)*q2
        coeff2 = np.sqrt(q1)*(1.-2.*q2)
    elif ld_law=='squareroot':
        coeff1 = np.sqrt(q1)*(1.-2.*q2)
        coeff2 = 2.*np.sqrt(q1)*q2
    elif ld_law=='logarithmic':
        coeff1 = 1.-np.sqrt(q1)*q2
        coeff2 = 1.-np.sqrt(q1)
    return coeff1,coeff2

def count_instruments(instrument_list):
    all_instruments = []
    for instrument in instrument_list:
        if instrument not in all_instruments:
            all_instruments.append(instrument)
    all_idxs = len(all_instruments)*[[]]
    all_ndata = len(all_instruments)*[[]]
    for i in range(len(all_instruments)):
        all_idxs[i] = np.where(all_instruments[i] == instrument_list)[0]
        all_ndata[i] = len(all_idxs[i])
    return all_instruments,all_idxs,np.array(all_ndata)

import emcee
import Wavelets
import scipy.optimize as op
import ajplanet as rv_model
def exonailer_mcmc_fit(times, relative_flux, error, tr_instruments, times_rv, rv, rv_err, rv_instruments,\
                       parameters, idx_resampling, options)
                       #ld_law, mode, rv_jitter = False, \
                       #njumps = 500, nburnin = 500, nwalkers = 100, noise_model = 'white',\
                       #resampling = False, idx_resampling = [], texp = 0.01881944, N_resampling = 5):
    """
    This function performs an MCMC fitting procedure using a transit model 
    fitted to input data using the batman package (Kreidberg, 2015) assuming 
    the underlying noise process is either 'white' or '1/f-like' (see Carter & 
    Winn, 2010). It makes use of the emcee package (Foreman-Mackey et al., 2014) 
    to perform the MCMC, and the sampling scheme explained in Kipping (2013) to 
    sample coefficients from two-parameter limb-darkening laws; the logarithmic 
    law is sampled according to Espinoza & Jordán (2016). 

    The inputs are:

      times:            Times (in same units as the period and time of transit center).

      relative_flux:    Relative flux; it is assumed out-of-transit flux is 1.

      error:            If you have errors on the fluxes, put them here. Otherwise, set 
                        this to None.

      tr_instruments:   Instruments of each time/flux pair.

      times_rv:         Times (in same units as the period and time of transit center) 
                        of RV data.

      rv:               Radial velocity measurements.

      rv_err:           If you have errors on the RVs, put them here. Otherwise, set 
                        this to None.

      rv_instruments:   Instruments of each time/RV pair.

      parameters:       Dictionary containing the information regarding the parameters (including priors).

      idx_resampling:   This defines the indexes over which you want to perform such resampling 
                        (selective resampling). It is a dictionary over the instruments; idx_resampling[instrument] 
                        has the indexes for the given instrument.

      options:          Dictionary containing the information inputted by the user.

      texp          :   Exposure time in days of each datapoint (default is Kepler long-cadence, 
                        taken from here: http://archive.stsci.edu/mast_faq.php?mission=KEPLER)

    The outputs are the chains of each of the parameters in the theta_0 array in the same 
    order as they were inputted. This includes the sampled parameters from all the walkers.
    """
    # If mode is not RV:
    if options['MODE'] != 'rv':
        params = {}
        m = {}
        t_resampling = {}
        transit_flat = {}
        # Count instruments:
        all_tr_instruments,all_tr_instruments_idxs,n_data_trs = count_instruments(tr_instruments)
        # Prepare data for batman:
        xt = times.astype('float64')
        yt = relative_flux.astype('float64')
        yerrt = error.astype('float64')
        for k in range(len(all_tr_instruments)):
            instrument = all_tr_instruments[k]
            params[instrument],m[instrument] = init_batman(xt[all_tr_instruments_idxs[k]],\
                                               law=options['photometry'][instrument]['LD_LAW'])
            # Initialize the parameters of the transit model, 
            # and prepare resampling data if resampling is True:
            if options['photometry'][instrument]['RESAMPLING']:
               t_resampling[instrument] = np.array([])
               for i in range(len(idx_resampling[instrument])):
                   tij = np.zeros(options['photometry'][instrument]['NRESAMPLING'])
                   for j in range(1,options['photometry'][instrument]['NRESAMPLING']+1):
                       # Eq (35) in Kipping (2010)    
                       tij[j-1] = xt[all_tr_instruments_idxs[k]][idx_resampling[instrument][i]] + ((j - \
                                  ((options['photometry'][instrument]['NRESAMPLING']+1)/2.))*(texp/np.double(\
                                  options['photometry'][instrument]['NRESAMPLING'])))
                   t_resampling[instrument] = np.append(t_resampling[instrument], np.copy(tij))

               params[instrument],m[instrument] = init_batman(t_resampling[instrument],\
                                                  law=options['photometry'][instrument]['LD_LAW'])
               transit_flat[instrument] = np.ones(len(xt[all_tr_instruments_idxs[k]]))
               transit_flat[instrument][idx_resampling[instrument]] = np.zeros(len(idx_resampling[instrument]))

    # Initialize the variable names:
    if len(all_tr_instruments)>1:
        transit_params = ['P','inc']
    else:
        the_instrument = options['photometry'].keys()[0]
        transit_params = ['P','inc','t0','a','p','inc','sigma_w','sigma_r','q1','q2']
    common_params = ['ecc','omega']
    rv_params = ['K']

    # If mode is not transit, prepare the data too:
    if 'transit' not in options['MODE']:
       xrv = times_rv.astype('float64')
       yrv = rv.astype('float64')
       if rv_err is None:
           yerrrv = 0.0
       else:
           yerrrv = rv_err.astype('float64')
       all_rv_instruments,all_rv_instruments_idxs,n_data_rvs = count_instruments(rv_instruments)

       if len(all_rv_instruments)>1:
          for instrument in all_rv_instruments:
              rv_params.append('mu_'+instrument)
              rv_params.append('sigma_w_rv_'+instrument)
       else:
          rv_params.append('mu')
          rv_params.append('sigma_w_rv')

    # Create lists that will save parameters to check the limits on:
    parameters_to_check = []

    # Check common parameters:
    if parameters['ecc']['type'] == 'FIXED':
       common_params.pop(common_params.index('ecc'))
    elif parameters['ecc']['type'] in ['Uniform','Jeffreys']:
       parameters_to_check.append('ecc')

    if parameters['omega']['type'] == 'FIXED':
       common_params.pop(common_params.index('omega'))
    elif parameters['omega']['type'] in ['Uniform','Jeffreys']:
       parameters_to_check.append('omega')


    # Eliminate from the parameter list parameters that are being fixed:
    if options['MODE'] != 'rv':
        if len(all_tr_instruments)>1:
            # First, generate a sufix dictionary, which will add the sufix _instrument to 
            # each instrument in the MCMC, in order to keep track of the parameters that 
            # are being held constant between instruments and those that vary with instrument:
            sufix = {}
            # Check parameters that always will be constant amongst transits:
            for par in ['P','inc']:
                if parameters[par]['type'] == 'FIXED':
                    transit_params.pop(transit_params.index(par))
                elif parameters[par]['type'] in ['Uniform','Jeffreys']:
                    parameters_to_check.append(par)

            # Now check parameters that might change between instruments:
            for i in range(len(all_tr_instruments)):
                instrument = all_tr_instruments[i]
                sufix[instrument] = {}
                for par in ['t0','a','p','sigma_w','q1','q2']:
                    orig_par = par
                    sufix[instrument][orig_par] = ''
                    if par not in parameters.keys():
                        par = par+'_'+instrument
                        sufix[instrument][orig_par] = '_'+instrument
                        if par not in parameters.keys():
                            print 'Error: parameter '+orig_par+' not defined. Exiting...'
                            sys.exit()
                    transit_params.append(par)    
                    if parameters[par]['type'] == 'FIXED':
                        transit_params.pop(transit_params.index(par))
                    elif parameters[par]['type'] in ['Uniform','Jeffreys']:
                        parameters_to_check.append(par)
                if options['photometry'][instrument]['PHOT_NOISE_MODEL'] == 'flicker':
                    transit_params.append('sigma_r_'+instrument)
                    if parameters['sigma_r_'+instrument]['type'] == 'FIXED':
                        transit_params.pop(transit_params.index('sigma_r_'+instrument))
                    elif parameters['sigma_r_'+instrument]['type'] in ['Uniform','Jeffreys']:
                        parameters_to_check.append('sigma_r_'+instrument)
                            
        else:
            for par in ['P','t0','a','p','inc','sigma_w','q1','q2']:
                 if parameters[par]['type'] == 'FIXED':
                     transit_params.pop(transit_params.index(par))
                 elif parameters[par]['type'] in ['Uniform','Jeffreys']:
                    parameters_to_check.append(par)
            if options['photometry'][options['photometry'].keys()[0]]['PHOT_NOISE_MODEL'] == 'flicker':
                if parameters['sigma_r']['type'] == 'FIXED':
                    transit_params.pop(transit_params.index('sigma_r'))
                elif parameters['sigma_r']['type'] in ['Uniform','Jeffreys']:
                    parameters_to_check.append('sigma_r')
            else:
                transit_params.pop(transit_params.index('sigma_r'))

    if options['MODE'] != 'transit':
        if parameters['K']['type'] == 'FIXED':
            rv_params.pop(rv_params.index('K'))
        elif parameters['K']['type'] in ['Uniform','Jeffreys']:
            parameters_to_check.append('K')
        if len(all_rv_instruments)>1:
            sigma_w_rv = {}
            for instrument in all_rv_instruments:
                if parameters['mu_'+instrument]['type'] == 'FIXED':
                    rv_params.pop(rv_params.index('mu_'+instrument))
                elif parameters['mu_'+instrument]['type'] in ['Uniform','Jeffreys']:
                    parameters_to_check.append('mu_'+instrument)
                if parameters['sigma_w_rv_'+instrument]['type'] == 'FIXED':
                    rv_params.pop(rv_params.index('sigma_w_rv_'+instrument))       
                elif parameters['sigma_w_rv_'+instrument]['type'] in ['Uniform','Jeffreys']:
                    parameters_to_check.append('sigma_w_rv_'+instrument)
                else: 
                    sigma_w_rv[instrument] = 0.0 
                    rv_params.pop(rv_params.index('sigma_w_rv_'+instrument))
        else:
            if parameters['K']['type'] == 'FIXED':
                rv_params.pop(rv_params.index('K'))
            elif parameters['K']['type'] in ['Uniform','Jeffreys']:
                parameters_to_check.append('K')
            if parameters['sigma_w_rv']['type'] == 'FIXED':
                rv_params.pop(rv_params.index('sigma_w_rv'))
            elif parameters['sigma_w_rv']['type'] in ['Uniform','Jeffreys']:
                parameters_to_check.append('sigma_w_rv')
            else:
                sigma_w_rv = 0.0
                rv_params.pop(rv_params.index('sigma_w_rv'))

    if options['MODE'] == 'transit':
       all_mcmc_params = transit_params + common_params
    elif options['MODE'] == 'rv':
       all_mcmc_params = rv_params + common_params
    elif options['MODE'] == 'transit_noise':
       all_mcmc_params = ['sigma_w','sigma_r']
    else:
       all_mcmc_params = transit_params + rv_params + common_params

    n_params = len(all_mcmc_params)
    log2pi = np.log(2.*np.pi)

    def normal_like(x,mu,tau):
        return 0.5*(np.log(tau) - log2pi - tau*( (x-mu)**2))

    def get_fn_likelihood(residuals, sigma_w, sigma_r, gamma=1.0):
        like=0.0
        # Arrays of zeros to be passed to the likelihood function
        aa,bb,M = Wavelets.getDWT(residuals)
        # Calculate the g(gamma) factor used in Carter & Winn...
        if(gamma==1.0):
           g_gamma=1.0/(2.0*np.log(2.0))  # (value assuming gamma=1)
        else:
           g_gamma=(2.0)-(2.0)**gamma
        # log-Likelihood of the aproximation coefficients
        sigmasq_S=(sigma_r**2)*g_gamma+(sigma_w)**2
        tau_a =  1.0/sigmasq_S
        like += normal_like( bb[0], 0.0 , tau_a )
        k=long(0)
        SS=range(M)
        for ii in SS:
                # log-Likelihood of the detail coefficients with m=i...
                if(ii==0):
                  sigmasq_W=(sigma_r**2)*(2.0**(-gamma*np.double(1.0)))+(sigma_w)**2
                  tau=1.0/sigmasq_W
                  like += normal_like( bb[1], 0.0, tau )
                else:
                  sigmasq_W=(sigma_r**2)*(2.0**(-gamma*np.double(ii+1)))+(sigma_w)**2
                  tau=1.0/sigmasq_W
                  for j in range(2**ii):
                      like += normal_like( aa[k], 0.0 , tau )
                      k=k+1
        return like

    def lnlike_transit(gamma=1.0):
        if len(all_tr_instruments) == 1:
            coeff1,coeff2 = reverse_ld_coeffs(options['photometry'][the_instrument]['LD_LAW'], \
                            parameters['q1']['object'].value,parameters['q2']['object'].value)
            params[the_instrument].t0 = parameters['t0']['object'].value
            params[the_instrument].per = parameters['P']['object'].value
            params[the_instrument].rp = parameters['p']['object'].value
            params[the_instrument].a = parameters['a']['object'].value
            params[the_instrument].inc = parameters['inc']['object'].value
            params[the_instrument].ecc = parameters['ecc']['object'].value
            params[the_instrument].w = parameters['omega']['object'].value
            params[the_instrument].u = [coeff1,coeff2]
            model = m[the_instrument].light_curve(params[the_instrument])
            if options['photometry'][the_instrument]['RESAMPLING']:
               for i in range(len(idx_resampling[the_instrument])):
                   transit_flat[the_instrument][idx_resampling[the_instrument][i]] = \
                   np.mean(model[i*options['photometry'][the_instrument]['NRESAMPLING']:options['photometry'][the_instrument]['RESAMPLING']*(i+1)])
               residuals = (yt-transit_flat[the_instrument])*1e6
            else:
               residuals = (yt-model)*1e6
            if options['photometry'][the_instrument]['PHOT_NOISE_MODEL'] == 'flicker':
               log_like = get_fn_likelihood(residuals,parameters['sigma_w']['object'].value,\
                               parameters['sigma_r']['object'].value)
            else:
               taus = 1.0/((yerrt*1e6)**2 + (parameters['sigma_w']['object'].value)**2)
               log_like = -0.5*(n_data_trs[0]*log2pi+np.sum(np.log(1./taus)+taus*(residuals**2)))
            return log_like
        else:
            log_like = 0.0
            sufix[instrument][orig_par]
            for k in range(len(all_tr_instruments)):
                instrument = all_tr_instruments[k]
                coeff1,coeff2 = reverse_ld_coeffs(options['photometry'][instrument]['LD_LAW'], \
                                parameters['q1'+sufix[instrument]['q1']]['object'].value,\
                                parameters['q2'+sufix[instrument]['q2']]['object'].value)
                params[instrument].t0 = parameters['t0'+sufix[instrument]['t0']]['object'].value
                params[instrument].per = parameters['P']['object'].value
                params[instrument].rp = parameters['p'+sufix[instrument]['p']]['object'].value
                params[instrument].a = parameters['a'+sufix[instrument]['a']]['object'].value
                params[instrument].inc = parameters['inc']['object'].value
                params[instrument].ecc = parameters['ecc']['object'].value
                params[instrument].w = parameters['omega']['object'].value
                params[instrument].u = [coeff1,coeff2]
                model = m[instrument].light_curve(params[instrument])
                if options['photometry'][instrument]['RESAMPLING']:
                   for i in range(len(idx_resampling[instrument])):
                       transit_flat[instrument][idx_resampling[instrument][i]] = \
                       np.mean(model[i*options['photometry'][instrument]['NRESAMPLING']:options['photometry'][instrument]['RESAMPLING']*(i+1)])
                   residuals = (yt[all_tr_instruments_idxs[k]]-transit_flat[instrument])*1e6
                else:
                   residuals = (yt[all_tr_instruments_idxs[k]]-model)*1e6
                if options['photometry'][instrument]['PHOT_NOISE_MODEL'] == 'flicker':
                   log_like = log_like + get_fn_likelihood(residuals,parameters['sigma_w'+sufix[instrument]['sigma_w']]['object'].value,\
                                   parameters['sigma_r'+sufix[instrument]['sigma_r']]['object'].value)
                else:
                   taus = 1.0/((yerrt[all_tr_instruments_idxs[k]]*1e6)**2 + (parameters['sigma_w'+sufix[instrument]['sigma_w']]['object'].value)**2)
                   log_like = log_like - 0.5*(n_data_trs[k]*log2pi+np.sum(np.log(1./taus)+taus*(residuals**2)))
            return log_like
            

    def lnlike_rv():
        if len(all_rv_instruments) == 1:
            model = rv_model.pl_rv_array(xrv,parameters['mu']['object'].value,parameters['K']['object'].value,\
                            parameters['omega']['object'].value*np.pi/180.,parameters['ecc']['object'].value,\
                            parameters['t0']['object'].value,parameters['P']['object'].value)
            residuals = (yrv-model)
            taus = 1.0/((yerrrv)**2 + (parameters['sigma_w_rv']['object'].value)**2)
            log_like = -0.5*(n_data_rvs[0]*log2pi+np.sum(np.log(1./taus)+taus*(residuals**2)))
            return log_like
        else:
            log_like = 0.0
            for i in range(len(all_rv_instruments)):
                model = rv_model.pl_rv_array(xrv[all_rv_instruments_idxs[i]],parameters['mu_'+all_rv_instruments[i]]['object'].value,\
                                parameters['K']['object'].value, parameters['omega']['object'].value*np.pi/180.,parameters['ecc']['object'].value,\
                                parameters['t0']['object'].value,parameters['P']['object'].value)
                residuals = (yrv[all_rv_instruments_idxs[i]]-model)
                taus = 1.0/((yerrrv[all_rv_instruments_idxs[i]])**2 + (parameters['sigma_w_rv_'+all_rv_instruments[i]]['object'].value)**2)
                log_like = log_like -0.5*(n_data_rvs[i]*log2pi+np.sum(np.log(1./taus)+taus*(residuals**2)))
            return log_like

    def lnprior(theta):
        # Read in the values of the parameter vector and update values of the objects.
        # For each one, if everything is ok, get the total prior, which is the sum 
        # of the independant priors for each parameter:
        total_prior = 0.0
        for i in range(n_params):
            c_param = all_mcmc_params[i]
            parameters[c_param]['object'].set_value(theta[i])
            if c_param in parameters_to_check:
                if not parameters[c_param]['object'].check_value(theta[i]):
                    return -np.inf
            total_prior += parameters[c_param]['object'].get_ln_prior()
        return total_prior

    def lnprob_full(theta):
        lp = lnprior(theta)
        if not np.isfinite(lp):
            return -np.inf
        return lp + lnlike_rv() + lnlike_transit()

    def lnprob_transit(theta):
        lp = lnprior(theta)
        if not np.isfinite(lp):
            return -np.inf
        return lp + lnlike_transit()

    def lnprob_rv(theta):
        lp = lnprior(theta)
        if not np.isfinite(lp):
            return -np.inf
        return lp + lnlike_rv()

    # Define the posterior to use:
    if mode == 'full':
        lnprob = lnprob_full 
    elif mode == 'transit':
        lnprob = lnprob_transit
    elif mode == 'rv':
        lnprob = lnprob_rv
    else:
        print 'Mode not supported. Doing nothing.'

    # If already not done, get posterior samples:
    if len(parameters[all_mcmc_params[0]]['object'].posterior) == 0:
        # Extract initial input values of the parameters to be fitted:
        theta_0 = []
        for i in range(n_params):
            theta_0.append(parameters[all_mcmc_params[i]]['object'].value)

        # Start at the maximum likelihood value:
        nll = lambda *args: -lnprob(*args)

        # Get ML estimate:
        result = op.minimize(nll, theta_0)
        theta_ml = result["x"]

        # Now define parameters for emcee:
        ndim = len(theta_ml)
        pos = [result["x"] + 1e-4*np.random.randn(ndim) for i in range(nwalkers)]
        # Run the MCMC:
        sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob)

        sampler.run_mcmc(pos, njumps+nburnin)

        # Save the parameter chains for the parameters that were actually varied:
        for i in range(n_params):
            c_param = all_mcmc_params[i]
            c_p_chain = np.array([])
            for walker in range(nwalkers):
                c_p_chain = np.append(c_p_chain,sampler.chain[walker,nburnin:,i])
            parameters[c_param]['object'].set_posterior(np.copy(c_p_chain))

    # When done or if MCMC already performed, save results:
    initial_values = {}
    for i in range(len(all_mcmc_params)):
        initial_values[all_mcmc_params[i]] = parameters[all_mcmc_params[i]]['object'].value

import matplotlib.pyplot as plt
def plot_transit(t,f,parameters,ld_law,transit_instruments,\
                 resampling = False, phase_max = 0.025, \
                 idx_resampling_pred = [], texp = 0.01881944, N_resampling = 5):
        
    # Extract transit parameters:
    P = parameters['P']['object'].value
    inc = parameters['inc']['object'].value
    a = parameters['a']['object'].value
    p = parameters['p']['object'].value
    t0 = parameters['t0']['object'].value
    q1 = parameters['q1']['object'].value
    q2 = parameters['q2']['object'].value

    # Get data phases:
    phases = get_phases(t,P,t0)

    # Generate model times by super-sampling the times:
    model_t = np.linspace(np.min(t),np.max(t),len(t)*N_resampling)
    model_phase = get_phases(model_t,P,t0)

    # Initialize the parameters of the transit model, 
    # and prepare resampling data if resampling is True:
    if resampling:
        idx_resampling = np.where((model_phase>-phase_max)&(model_phase<phase_max))[0]
        t_resampling = np.array([])
        for i in range(len(idx_resampling)):
            tij = np.zeros(N_resampling)
            for j in range(1,N_resampling+1):
                # Eq (35) in Kipping (2010)    
                tij[j-1] = model_t[idx_resampling[i]] + ((j - ((N_resampling+1)/2.))*(texp/np.double(N_resampling)))
            t_resampling = np.append(t_resampling, np.copy(tij))

        idx_resampling_pred = np.where((phases>-phase_max)&(phases<phase_max))[0]
        t_resampling_pred = np.array([])
        for i in range(len(idx_resampling_pred)):
            tij = np.zeros(N_resampling)
            for j in range(1,N_resampling+1):
                tij[j-1] = t[idx_resampling_pred[i]] + ((j - ((N_resampling+1)/2.))*(texp/np.double(N_resampling)))
            t_resampling_pred = np.append(t_resampling_pred, np.copy(tij))
        params,m = init_batman(t_resampling, law=ld_law)
        params2,m2 = init_batman(t_resampling_pred, law=ld_law)
        transit_flat = np.ones(len(model_t))
        transit_flat[idx_resampling] = np.zeros(len(idx_resampling))
        transit_flat_pred = np.ones(len(t))
        transit_flat_pred[idx_resampling_pred] = np.zeros(len(idx_resampling_pred))

    else:
        params,m = init_batman(model_t,law=ld_law)
        params2,m2 = init_batman(t,law=ld_law)
    #####################################################################

    coeff1,coeff2 = reverse_ld_coeffs(ld_law, q1, q2)
    params.t0 = t0
    params.per = P
    params.rp = p
    params.a = a
    params.inc = inc
    params.u = [coeff1,coeff2]

    # Generate model and predicted lightcurves:
    if resampling:
        model = m.light_curve(params)
        for i in range(len(idx_resampling)):
            transit_flat[idx_resampling[i]] = np.mean(model[i*N_resampling:N_resampling*(i+1)])
        model_lc = transit_flat

        model = m2.light_curve(params)
        for i in range(len(idx_resampling_pred)):
            transit_flat_pred[idx_resampling_pred[i]] = np.mean(model[i*N_resampling:N_resampling*(i+1)])
        model_pred = transit_flat_pred
    else:
        model_lc = m.light_curve(params)
        model_pred = m2.light_curve(params)

    # Now plot:
    plt.style.use('ggplot')
    plt.title('exonailer final fit + phased data')
    plt.xlabel('Phase')
    plt.ylabel('Relative flux')
    idx = np.argsort(model_phase)
    plt.plot(phases,f,'.',color='black',alpha=0.4)
    plt.plot(model_phase[idx],model_lc[idx])
    idx_ph = np.argsort(phases)
    plt.plot(phases[idx_ph],np.ones(len(phases))*(1-2.5*p**2),'--',color='r')
    plt.plot(phases,(f-model_pred) + (1-2.5*p**2),'.',color='black',alpha=0.4)
    plt.show()

def plot_transit_and_rv(t,f,trv,rv,rv_err,parameters,ld_law,rv_jitter,transit_instruments,rv_instruments,\
                        resampling = False, phase_max = 0.025, texp = 0.01881944, N_resampling = 5):
    # Extract parameters:
    P = parameters['P']['object'].value
    inc = parameters['inc']['object'].value
    a = parameters['a']['object'].value
    p = parameters['p']['object'].value
    t0 = parameters['t0']['object'].value
    q1 = parameters['q1']['object'].value
    q2 = parameters['q2']['object'].value
    K = parameters['K']['object'].value
    ecc = parameters['ecc']['object'].value
    omega = parameters['omega']['object'].value
    all_rv_instruments,all_rv_instruments_idxs,n_data_rvs = count_instruments(rv_instruments)
    if len(all_rv_instruments)>1:
        mu = {}
        for instrument in all_rv_instruments:
            mu[instrument] = parameters['mu_'+instrument]['object'].value
    else:
        mu = parameters['mu']['object'].value
        print mu

    # Get data phases:
    phases = get_phases(t,P,t0)

    # Generate model times by super-sampling the times:
    model_t = np.linspace(np.min(t),np.max(t),len(t)*4)
    model_phase = get_phases(model_t,P,t0)

    # Initialize the parameters of the transit model, 
    # and prepare resampling data if resampling is True:
    if resampling:
        idx_resampling = np.where((model_phase>-phase_max)&(model_phase<phase_max))[0]
        t_resampling = np.array([])
        for i in range(len(idx_resampling)):
            tij = np.zeros(N_resampling)
            for j in range(1,N_resampling+1):
                # Eq (35) in Kipping (2010)    
                tij[j-1] = model_t[idx_resampling[i]] + ((j - ((N_resampling+1)/2.))*(texp/np.double(N_resampling)))
            t_resampling = np.append(t_resampling, np.copy(tij))    

        idx_resampling_pred = np.where((phases>-phase_max)&(phases<phase_max))[0]
        t_resampling_pred = np.array([])
        for i in range(len(idx_resampling_pred)):
            tij = np.zeros(N_resampling)
            for j in range(1,N_resampling+1):
                tij[j-1] = t[idx_resampling_pred[i]] + ((j - ((N_resampling+1)/2.))*(texp/np.double(N_resampling)))
            t_resampling_pred = np.append(t_resampling_pred, np.copy(tij))
        params,m = init_batman(t_resampling, law=ld_law)
        params2,m2 = init_batman(t_resampling_pred, law=ld_law)
        transit_flat = np.ones(len(model_t))
        transit_flat[idx_resampling] = np.zeros(len(idx_resampling))
        transit_flat_pred = np.ones(len(t))
        transit_flat_pred[idx_resampling_pred] = np.zeros(len(idx_resampling_pred))

    else:
        params,m = init_batman(model_t,law=ld_law)
        params2,m2 = init_batman(t,law=ld_law)

    coeff1,coeff2 = reverse_ld_coeffs(ld_law, q1, q2)
    params.t0 = t0
    params.per = P
    params.rp = p
    params.a = a
    params.inc = inc
    params.ecc = ecc
    params.omega = omega
    params.u = [coeff1,coeff2]

    # Generate model and predicted lightcurves:
    if resampling:
        model = m.light_curve(params)
        for i in range(len(idx_resampling)):
            transit_flat[idx_resampling[i]] = np.mean(model[i*N_resampling:N_resampling*(i+1)])
        model_lc = transit_flat

        model = m2.light_curve(params)
        for i in range(len(idx_resampling_pred)):
            transit_flat_pred[idx_resampling_pred[i]] = np.mean(model[i*N_resampling:N_resampling*(i+1)])
        model_pred = transit_flat_pred
    else:
        model_lc = m.light_curve(params)
        model_pred = m2.light_curve(params)

    # Now plot:
    plt.style.use('ggplot')
    plt.subplot(211)
    #plt.xlabel('Phase')
    plt.title('exonailer final fit + data')
    plt.ylabel('Relative flux')
    idx = np.argsort(model_phase)
    plt.plot(phases,f,'.',color='black',alpha=0.4)
    plt.plot(model_phase[idx],model_lc[idx])
    plt.plot(phases,f-model_pred+(1-1.8*(p**2)),'.',color='black',alpha=0.4)

    plt.subplot(212)
    plt.ylabel('Radial velocity (m/s)')
    plt.xlabel('Phase')
    model_rv = rv_model.pl_rv_array(model_t,0.0,K,omega*np.pi/180.,ecc,t0,P)
    predicted_rv = rv_model.pl_rv_array(trv,0.0,K,omega*np.pi/180.,ecc,t0,P)
    if len(all_rv_instruments)>1:
        for i in range(len(all_rv_instruments)):
            rv_phases = get_phases(trv[all_rv_instruments_idxs[i]],P,t0)
            plt.errorbar(rv_phases,(rv[all_rv_instruments_idxs[i]]-mu[all_rv_instruments[i]])*1e3,yerr=rv_err[all_rv_instruments_idxs[i]]*1e3,fmt='o',label='RVs from '+all_rv_instruments[i])
        plt.legend()
    else:
        rv_phases = get_phases(trv,P,t0)
        plt.errorbar(rv_phases,(rv-mu)*1e3,yerr=rv_err*1e3,fmt='o')
    plt.plot(model_phase[idx],(model_rv[idx])*1e3)
    plt.show()
    opt = raw_input('\t Save lightcurve and RV data and models? (y/n)')
    if opt == 'y':
        fname = raw_input('\t Output filename (without extension): ')   
        fout = open('results/'+fname+'_lc_data.dat','w')
        fout.write('# Time    Phase     Normalized flux \n')
        for i in range(len(phases)):
            fout.write(str(t[i])+' '+str(phases[i])+' '+str(f[i])+'\n')
        fout.close()
        fout = open('results/'+fname+'_lc_model.dat','w')
        fout.write('# Phase     Normalized flux \n')
        for i in range(len(model_phase[idx])):
            fout.write(str(model_phase[idx][i])+' '+str(model_lc[idx][i])+'\n')
        fout.close()
        fout = open('results/'+fname+'_o-c_lc.dat','w')
        for i in range(len(phases)):
            fout.write(str(t[i])+' '+str(phases[i])+' '+str(f[i]-model_pred[i])+'\n')
        fout.close()
        fout = open('results/'+fname+'_rvs_data.dat','w')
        fout2 = open('results/'+fname+'_o-c_rvs.dat','w')
        fout.write('# Phase     RV (m/s)  Error (m/s)  Instrument\n')
        if len(all_rv_instruments)>1:
            for i in range(len(all_rv_instruments)):
                rv_phases = get_phases(trv[all_rv_instruments_idxs[i]],P,t0)
                for j in range(len(rv_phases)):
                    fout.write(str(rv_phases[j])+' '+str(((rv[all_rv_instruments_idxs[i]]-mu[all_rv_instruments[i]])*1e3)[j])+\
                                    ' '+str(((rv_err[all_rv_instruments_idxs[i]])*1e3)[j])+\
                                    ' '+all_rv_instruments[i]+'\n')
        else:
            for i in range(len(rv_phases)):
                fout.write(str(rv_phases[i])+' '+str((rv[i]-mu)*1e3)+' '+str(rv_err[i]*1e3)+' \n')
                fout2.write(str(rv_phases[i])+' '+str((rv[i]-mu-predicted_rv[i])*1e3)+' '+str(rv_err[i]*1e3)+' \n')
        fout.close()
        fout2.close()
        fout = open('results/'+fname+'_rvs_model.dat','w')
        fout.write('# Phase     RV (m/s) \n')
        for i in range(len(model_phase[idx])):
            fout.write(str(model_phase[idx][i])+' '+str(((model_rv[idx])*1e3)[i])+'\n')
        fout.close()
