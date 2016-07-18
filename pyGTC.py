from matplotlib import pyplot as plt
import numpy as np
import scipy.ndimage
from matplotlib.ticker import MaxNLocator
from scipy.stats import norm

def plotGTC(chains, **kwargs):
    """Create a beautiful triangle plot - aka Giant Triangle Confusogram (GTC).

    Parameters:
    -----------
    chains: 2d array or list of 2d arrays
        Sample points (length x Ndim) or multiple sets of samples points
        Note: If you are using emcee (http://dan.iel.fm/emcee/current/) - and you should! - you need to pass the EnsembleSampler.flatchain object.
    kwargs:
        See below for all arguments.

    Returns:
    --------
    fig: matplotlib.figure
        the GTC in all its glory
    """
    # Set defaults
    #TODO: make default labels be 1, 2, 3, etc...

    priors=None # Draw a Gaussian distribution (or several) in the 1d panels
    weights=None # Provide weight factors for your sample points
    plotName=None # Save plot as plotName, else return matplotlib.figure object
    figureSize=None # Width=height of figure in inches
    chainLabels=None # Create legend with names for the plotted data
    truthLabels=None # Label the truth lines in the legend
    nConfidenceLevels=2 # Draw 2d contours out to the nConfidenceLevels level, support 1, 2, 3
    smoothingKernel=1 # Gaussian smoothing kernel (in pixels)

    #Numpy really doesn't like lists of Pandas DataFrame objects
    #so if it gets one, extract array vals and throw away the rest
    try: #Not a list of DFs, but might be a single DF
        shapeLength = len(np.shape(chains))
        assert shapeLength in [2,3], "unexpected chains shape"
        if shapeLength == 2:
            chains = [chains]

        # Read in column names from Pandas DataFrame if exists
        #Also convert DataFrame to simple numpy array to avoid later conflicts
        if hasattr(chains[0], 'columns'):
            paramNames = list(chains[0].columns.values)
            chains = [df.values for df in chains]

    except ValueError: #Probably a list of pandas DFs
        if hasattr(chains[0], 'columns') and hasattr(chains[0], 'values'):
            paramNames = list(chains[0].columns.values)
            chains = [df.values for df in chains]

        #If not a DF but something else, this will fail again, which is good
        assert len(np.shape(chains)) in [2,3], "unexpected chains shape"

    # Parse kwargs

    paramNames = kwargs.pop('paramNames', None) # label the x and y axes, supports latex
    if paramNames is not None:
        if all(isinstance(s, basestring) for s in paramNames):
            if len(paramNames) == len(chains[0][0,:]):
                paramNames = list(val)
            else:
                raise ValueError("paramNames length must match number of parameters in chains")
        else:
            raise TypeError("paramNames must be a list of strings")

    truthColors = kwargs.pop('truthColors', ['r','c','g','b','m'])
    truths = kwargs.pop('truths', None) # Highlight a point (or several) in parameter space by lines

    # Increase dimensionality of truth list by one if single list
    if truths is not None:
        try: #calling len(scalar) will raise a TypeError
            for ts in truths:
                if len(ts)<len(truthColors):
                    raise ValueError("More truths than available colors. Set colors with truthColors = [colors...]")
        except TypeError: #Probably a single list, so raise dimensionality
            truths = [truths]

        #Now if this raises a TypeError it's for a good reason
        for ts in truths:
            if len(ts)<len(truthColors):
                raise ValueError("More truths than available colors. Set colors with truthColors = [colors...]")


    if kwargs is not None:
        for key, val in kwargs.iteritems():
            if key == 'priors':
                priors = val
            elif key == 'weights':
                weights = val
            elif key == 'plotName':
                plotName = val
            elif key == 'figureSize':
                figureSize = val
            elif key == 'chainLabels':
                chainLabels = val
            elif key == 'truthLabels':
                truthLabels = val
            elif key == 'nConfidenceLevels':
                assert nConfidenceLevels in [1,2,3], "nConfidenceLevels must be 1, 2, or 3"
                nConfidenceLevels = val
            elif key == 'smoothingKernel':
                smoothingKernel = val
            else:
                raise NameError("illegal keyword argument: " + key)

    # Setup figure and colors
    plt.rcParams['legend.fontsize'] = 9
    plt.rcParams['axes.labelsize'] = 9
    plt.rcParams['xtick.labelsize'] = 5
    plt.rcParams['ytick.labelsize'] = 5
    plt.rcParams['text.usetex'] = True
    plt.rcParams['text.latex.preamble'] = [r'\usepackage{sansmath}', r'\sansmath']
    colors = [['#4c72b0','#7fa5e3','#b2d8ff'],
        ['#55a868','#88db9b','#bbffce'],
        ['#f5964f','#ffc982','#fffcb5'],
        ['#c44e52','#f78185','#ffb4b8'],
        ['#8172b2','#b4a5e5','#37d8ff'],
        ['#000000','#333333','#666666']]
    lightBlack = '#333333'

    # Number of chains
    nChains = len(chains)

    assert nChains<len(colors), "currently only supports up to "+str(len(colors))+" chains"

    # Check that chains are 2d arrays
    for i in range(nChains):
        assert len(np.shape(chains[i]))==2, "chain "+str(i)+" has unexpected shape"

    # Number of dimensions
    ndim = len(chains[0][0,:])

    # Manage the sample point weights
    if weights==None:
        # Set unit weights if no weights are provided
        weights = []
        for i in range(nChains):
            weights.append( np.ones(len(chains[i])) )
    else:
        if len(np.shape(weights))==len(chains[0]):
            weights = [weights]
        for i in range(nChains):
            if len(weights[i])!=len(chains[i]):
                raise ValueError("missmatch in chain/weights #%d: len(chain) %d, len(weights) %d"%(i,len(chains[i]),len(weights[i])))

    # Use the 68%, 95%, 99% confidence levels
    gaussConfLevels = [.3173, .0455, .0027]

    # These are needed to compute the confidence levels
    nBins = 30.
    nBinsFlat = np.linspace(0., nBins**2, nBins**2)

    # Left and right panel boundaries
    xmin, xmax = np.empty(ndim), np.empty(ndim)

    # Figure size (or resolution)
    if figureSize is None:
        # If no figure size is given, use resolution of 70 ppp (pixel per panel)
        figureWidth = ndim*70. / 72.27
    else:
        # User-defined width=height in inches
        if not isinstance(figureSize, basestring):
            figureWidth = figureSize
        else:
            # Choose from a couple of presets to fit your publication
            if figureSize=='APJ_column':
                figureWidth = 245.26653 / 72.27
            elif figureSize=='APJ_page':
                figureWidth = 513.11743 / 72.27
            elif figureSize=='MNRAS_column':
                figureWidth = 240. / 72.27
            elif figureSize=='MNRAS_page':
                figureWidth = 504. / 72.27
            else:
                raise ValueError("figureSize %s unknown!"%figureSize)
    fig = plt.figure(figsize=(figureWidth,figureWidth))



    ########## 2D contour plots

    chainLevels = np.ones((nChains,nConfidenceLevels+1))
    extents = np.empty((nChains,4))

    for i in range(ndim): # row
        for j in range(ndim): # column
            if j<i:
                ax = fig.add_subplot(ndim,ndim,(i*ndim)+j+1)


                ##### The filled contour plots
                smoothData = []
                # Draw filled contours in reversed order to have first chain in list on top
                for k in reversed(range(nChains)):
                    # Create 2d histogram
                    hist2d, xedges, yedges = np.histogram2d(chains[k][:,j], chains[k][:,i], weights=weights[k], bins=nBins)
                    # image extent, needed below for contour lines
                    extents[k] = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
                    # Normalize
                    hist2d = hist2d/np.sum(hist2d)
                    # Cumulative 1d distribution
                    histOrdered = np.sort(hist2d.flat)
                    histCumulative = np.cumsum(histOrdered)

                    # Compute confidence levels (from low to high for technical reasons)
                    for l in range(nConfidenceLevels):
                        # Find location of confidence level in 1d histCumulative
                        temp = np.interp(gaussConfLevels[l], histCumulative, nBinsFlat)
                        # Find "height" of confidence level
                        chainLevels[k][nConfidenceLevels-1-l] = np.interp(temp, nBinsFlat, histOrdered)

                    # Get bin center of histogram edges
                    xbins = np.delete(xedges+.5*(xedges[1]-xedges[0]), -1)
                    ybins = np.delete(yedges+.5*(yedges[1]-yedges[0]), -1)

                    # Apply Gaussian smoothing and plot
                    smoothData.append( scipy.ndimage.gaussian_filter(hist2d.T, sigma=smoothingKernel) )
                    ax.contourf(xbins, ybins, smoothData[-1], levels=chainLevels[k], colors=colors[k][:nConfidenceLevels][::-1])


                ###### Draw contour lines in order to see contours lying on top of each other
                for k in range(nChains):
                    for l in range(nConfidenceLevels):
                        ax.contour(smoothData[nChains-1-k], [chainLevels[k][nConfidenceLevels-1-l]], extent=extents[k], origin='lower', colors=colors[k][l])


                ##### Truth lines
                if truths is not None:
                    for k in range(len(truths)):
                        # horizontal line
                        if i < len(truths[k]):
                            if truths[k][i] is not None:
                                ax.axhline(truths[k][i], color=truthColors[k])
                        # vertical line
                        if j < len(truths[k]):
                            if truths[k][j] is not None:
                                ax.axvline(truths[k][j], color=truthColors[k])
                                # If needed, readjust limits of x_axis
                                lo, hi = ax.get_xlim()
                                if lo>truths[k][j]: lo = truths[k][j]-.05*(hi-lo)
                                if hi<truths[k][j]: hi = truths[k][j]+.05*(hi-lo)
                                ax.set_xlim(lo, hi)


                ##### Ticks & labels

                # x-labels at bottom of plot only
                if i==ndim-1:
                    if paramNames is not None:
                        ax.set_xlabel(paramNames[j])
                else:
                    ax.get_xaxis().set_ticklabels([])

                # y-labels for left-most panels only
                if j==0:
                    if paramNames is not None:
                        ax.set_ylabel(paramNames[i])
                else:
                    ax.get_yaxis().set_ticklabels([])

                # No more than 5 ticks per panel
                myLocator = MaxNLocator(5)
                ax.xaxis.set_major_locator(myLocator)
                myLocator = MaxNLocator(5)
                ax.yaxis.set_major_locator(myLocator)

                # Limits to be applied to 1d histograms
                xmin[j], xmax[j] = ax.get_xlim()



    ########## 1D histograms
    for i in range(ndim):
        ax = fig.add_subplot(ndim,ndim,(i*ndim)+i+1)

        ##### 1D histogram
        for k in reversed(range(nChains)):
            # create 1d histogram
            hist1d, edges = np.histogram(chains[k][:,i], weights = weights[k], normed=True, bins=nBins)
            # Bin center between histogram edges
            centers = np.delete(edges+.5*(edges[1]-edges[0]), -1)
            # Gaussian smoothing
            plotData = scipy.ndimage.gaussian_filter1d((centers,hist1d), sigma=smoothingKernel)
            # Filled histogram
            plt.fill_between(plotData[0], plotData[1], 0, color=colors[k][1])
            # Dotted line for hidden histogram
            plt.plot(plotData[0], plotData[1], ls=':', color=colors[k][1])


        ##### Truth line
        if truths is not None:
            for k in range(len(truths)):
                if i < len(truths[k]):
                    if truths[k][i] is not None:
                        ax.axvline(truths[k][i], color=truthColors[k])


        ##### Gaussian prior
        if priors is not None:
            if i < len(priors):
                if priors[i]:
                    if priors[i][1]>0:
                        if i==ndim-1:
                            arr = np.linspace(ax.get_xlim()[0],ax.get_xlim()[1],40)
                            plt.plot(arr,norm.pdf(arr,priors[i][0],priors[i][1]), color=lightBlack)
                        else:
                            arr = np.linspace(xmin[i],xmax[i],40)
                            plt.plot(arr,norm.pdf(arr,priors[i][0],priors[i][1]), color=lightBlack)


        ##### Ticks, labels, range

        # No labels on y-axes, lower limit 0
        ax.get_yaxis().set_ticklabels([])
        ax.set_ylim(bottom=0)

        # x-label for bottom-right panel only
        if i==ndim-1:
            if paramNames is not None:
                ax.set_xlabel(paramNames[i])
        else:
            ax.set_xlim(xmin[i],xmax[i])
            ax.get_xaxis().set_ticklabels([])

        # y label for top-left panel
        if i==0:
            if paramNames is not None:
                ax.set_ylabel(paramNames[i])

        # No more than 5 ticks per panel
        myLocator = MaxNLocator(5)
        ax.xaxis.set_major_locator(myLocator)
        myLocator = MaxNLocator(5)
        ax.yaxis.set_major_locator(myLocator)



    ########## Legend
    if (chainLabels is not None) or (truthLabels is not None):
        ##### Dummy plot for label line color
        labelColors = []
        ax = fig.add_subplot(ndim,ndim,ndim)
        ax.axis('off')

        ##### Label the data sets
        if chainLabels is not None:
            # Label for each chain
            for k in range(nChains):
                ax.plot(0,0, color=colors[k][0], label=chainLabels[k])
                labelColors.append(colors[k][0])

        ##### Label the truth lines
        if truthLabels is not None:
            # Label for each truth
            for k in range(len(truthLabels)):
                ax.plot(0,0, color=truthColors[k], label=truthLabels[k])
                labelColors.append(truthColors[k])

        ##### Legend and label colors according to plot
        leg = plt.legend(loc='upper right', fancybox=True)
        leg.get_frame().set_alpha(0.)
        for color,text in zip(labelColors,leg.get_texts()):
            text.set_color(color)



    ##########

    # No space between panels
    fig.subplots_adjust(hspace=0)
    fig.subplots_adjust(wspace=0)

    # Save figure
    if plotName is not None:
        plt.savefig(plotName, bbox_inches='tight')

    return fig
